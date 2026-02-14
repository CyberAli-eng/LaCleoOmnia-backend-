"""
Shopify Fulfillment Sync Service

This service handles fetching fulfillment data from Shopify and storing it in the order_shipments table.
It provides real-time tracking information for orders that have been fulfilled in Shopify.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import (
    Order,
    OrderShipment,
    OrderStatus,
    FulfillmentStatus
)
from app.services.shopify import ShopifyService

logger = logging.getLogger(__name__)


class ShopifyFulfillmentService:
    """Service for syncing Shopify fulfillments with local database."""
    
    def __init__(self, db: Session):
        self.db = db
        self.shopify_service = None
    
    def _get_shopify_service(self, user_id: str) -> Optional[ShopifyService]:
        """Get Shopify service instance for the user."""
        try:
            # Import here to avoid circular imports
            from app.http.controllers.integrations import _get_user_shopify_context
            
            # We need a user object, so we'll get it from the order
            # This is a simplified approach - in production, you'd pass user_id properly
            from app.models import User
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"User {user_id} not found")
                return None
                
            shop_domain, access_token, app_secret, integration_row = _get_user_shopify_context(self.db, user)
            if not access_token:
                logger.error(f"No Shopify access token for user {user_id}")
                return None
                
            return ShopifyService(shop_domain, access_token)
        except Exception as e:
            logger.error(f"Failed to get Shopify service: {e}")
            return None
    
    def fetch_order_fulfillments(self, order_id: str, user_id: str) -> List[Dict[str, Any]]:
        """
        Fetch fulfillments for a specific order from Shopify.
        
        Args:
            order_id: The local order ID
            user_id: The user ID for authentication
            
        Returns:
            List of fulfillment data from Shopify
        """
        try:
            shopify_service = self._get_shopify_service(user_id)
            if not shopify_service:
                return []
            
            # Get the order to find Shopify order ID
            order = self.db.query(Order).filter(Order.id == order_id).first()
            if not order:
                logger.error(f"Order {order_id} not found")
                return []
            
            if not order.channel_order_id:
                logger.warning(f"Order {order_id} has no channel_order_id")
                return []
            
            # Fetch fulfillments from Shopify
            fulfillments = shopify_service.get_order_fulfillments(order.channel_order_id)
            
            logger.info(f"Fetched {len(fulfillments)} fulfillments for order {order.channel_order_id}")
            return fulfillments
            
        except Exception as e:
            logger.error(f"Failed to fetch fulfillments for order {order_id}: {e}")
            return []
    
    def normalize_fulfillment_data(self, fulfillment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize Shopify fulfillment data to our database format.
        
        Args:
            fulfillment: Raw fulfillment data from Shopify
            
        Returns:
            Normalized data for order_shipments table
        """
        return {
            "shopify_fulfillment_id": str(fulfillment.get("id", "")),
            "tracking_number": fulfillment.get("tracking_number", "") or "",
            "courier": fulfillment.get("tracking_company", "") or "",
            "fulfillment_status": fulfillment.get("status", "") or "",
            "tracking_url": fulfillment.get("tracking_url", "") or "",
            "created_at": datetime.now(timezone.utc)
        }
    
    def upsert_shipment(self, order_id: str, fulfillment_data: Dict[str, Any]) -> bool:
        """
        Insert or update shipment data for an order.
        
        Args:
            order_id: Local order ID
            fulfillment_data: Normalized fulfillment data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            shopify_fulfillment_id = fulfillment_data["shopify_fulfillment_id"]
            
            # Check if shipment already exists
            existing_shipment = self.db.query(OrderShipment).filter(
                OrderShipment.order_id == order_id,
                OrderShipment.shopify_fulfillment_id == shopify_fulfillment_id
            ).first()
            
            if existing_shipment:
                # Update existing shipment (but preserve manual changes)
                existing_shipment.tracking_number = fulfillment_data["tracking_number"]
                existing_shipment.courier = fulfillment_data["courier"]
                existing_shipment.fulfillment_status = fulfillment_data["fulfillment_status"]
                existing_shipment.last_synced = fulfillment_data["created_at"]
                
                logger.info(f"Updated shipment {existing_shipment.id} for order {order_id}")
            else:
                # Create new shipment
                shipment = OrderShipment(
                    order_id=order_id,
                    shopify_fulfillment_id=shopify_fulfillment_id,
                    tracking_number=fulfillment_data["tracking_number"],
                    courier=fulfillment_data["courier"],
                    fulfillment_status=fulfillment_data["fulfillment_status"],
                    delivery_status="PENDING",  # Will be updated by Selloship worker
                    selloship_status=None,  # Will be updated by Selloship worker
                    last_synced=fulfillment_data["created_at"]
                )
                self.db.add(shipment)
                logger.info(f"Created shipment for order {order_id} with tracking {fulfillment_data['tracking_number']}")
            
            self.db.commit()
            return True
            
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Integrity error upserting shipment: {e}")
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upsert shipment: {e}")
            return False
    
    def sync_order_fulfillments(self, order_id: str, user_id: str) -> Dict[str, Any]:
        """
        Complete fulfillment sync for a single order.
        
        Args:
            order_id: Local order ID
            user_id: User ID for authentication
            
        Returns:
            Sync result with counts and status
        """
        try:
            # Fetch fulfillments from Shopify
            fulfillments = self.fetch_order_fulfillments(order_id, user_id)
            
            if not fulfillments:
                return {
                    "success": True,
                    "message": "No fulfillments found in Shopify",
                    "synced": 0,
                    "updated": 0
                }
            
            synced_count = 0
            updated_count = 0
            
            for fulfillment in fulfillments:
                normalized_data = self.normalize_fulfillment_data(fulfillment)
                
                # Only process if tracking number exists
                if normalized_data["tracking_number"]:
                    if self.upsert_shipment(order_id, normalized_data):
                        # Check if this was an update or new insert
                        existing = self.db.query(OrderShipment).filter(
                            OrderShipment.order_id == order_id,
                            OrderShipment.shopify_fulfillment_id == normalized_data["shopify_fulfillment_id"]
                        ).first()
                        
                        if existing:
                            updated_count += 1
                        else:
                            synced_count += 1
                else:
                    logger.warning(f"Skipping fulfillment {normalized_data['shopify_fulfillment_id']} - no tracking number")
            
            return {
                "success": True,
                "message": f"Synced {synced_count} new, updated {updated_count} shipments",
                "synced": synced_count,
                "updated": updated_count,
                "total": synced_count + updated_count
            }
            
        except Exception as e:
            logger.error(f"Failed to sync fulfillments for order {order_id}: {e}")
            return {
                "success": False,
                "message": f"Sync failed: {str(e)}",
                "synced": 0,
                "updated": 0
            }
    
    def sync_all_pending_orders(self, user_id: str) -> Dict[str, Any]:
        """
        Sync fulfillments for all orders that don't have shipments yet.
        
        Args:
            user_id: User ID for authentication
            
        Returns:
            Overall sync result
        """
        try:
            # Get orders that don't have shipments yet
            orders_without_shipments = self.db.query(Order).filter(
                ~Order.shipments.any()  # Using relationship to check for existing shipments
            ).all()
            
            total_synced = 0
            total_updated = 0
            failed_orders = []
            
            logger.info(f"Found {len(orders_without_shipments)} orders without shipments")
            
            for order in orders_without_shipments:
                result = self.sync_order_fulfillments(str(order.id), user_id)
                
                if result["success"]:
                    total_synced += result["synced"]
                    total_updated += result["updated"]
                else:
                    failed_orders.append({
                        "order_id": order.id,
                        "channel_order_id": order.channel_order_id,
                        "error": result["message"]
                    })
            
            return {
                "success": len(failed_orders) == 0,
                "message": f"Processed {len(orders_without_shipments)} orders: {total_synced} new, {total_updated} updated",
                "total_orders": len(orders_without_shipments),
                "synced": total_synced,
                "updated": total_updated,
                "failed_orders": failed_orders
            }
            
        except Exception as e:
            logger.error(f"Failed to sync all pending orders: {e}")
            return {
                "success": False,
                "message": f"Batch sync failed: {str(e)}",
                "total_orders": 0,
                "synced": 0,
                "updated": 0,
                "failed_orders": []
            }


def sync_fulfillments_for_order(order_id: str, user_id: str, db: Session) -> Dict[str, Any]:
    """
    Convenience function to sync fulfillments for a single order.
    
    Args:
        order_id: Local order ID
        user_id: User ID for authentication
        db: Database session
        
    Returns:
        Sync result
    """
    service = ShopifyFulfillmentService(db)
    return service.sync_order_fulfillments(order_id, user_id)


def sync_all_pending_fulfillments(user_id: str, db: Session) -> Dict[str, Any]:
    """
    Convenience function to sync all pending fulfillments.
    
    Args:
        user_id: User ID for authentication
        db: Database session
        
    Returns:
        Overall sync result
    """
    service = ShopifyFulfillmentService(db)
    return service.sync_all_pending_orders(user_id)
