"""
Shopify Fulfillment Sync Service
Fetches fulfillments from Shopify and stores tracking information
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models import Order, OrderShipment, Channel, ChannelAccount
from app.services.shopify import ShopifyService

logger = logging.getLogger(__name__)


class ShopifyFulfillmentSync:
    """Shopify fulfillment synchronization service"""
    
    def __init__(self, db: Session):
        self.db = db
        
    def get_shopify_account(self) -> Optional[ChannelAccount]:
        """Get Shopify account from database"""
        shopify_channel = self.db.query(Channel).filter(Channel.name == 'SHOPIFY').first()
        if not shopify_channel:
            logger.error("No SHOPIFY channel found")
            return None
            
        return self.db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == shopify_channel.id
        ).first()
    
    async def sync_fulfillments_for_order(self, order_id: str) -> Dict:
        """
        Sync fulfillments for a specific order
        """
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return {"status": "FAILED", "error": f"Order {order_id} not found"}
            
        if not order.channel_order_id:
            return {"status": "FAILED", "error": f"Order {order_id} has no channel_order_id"}
            
        shopify_account = self.get_shopify_account()
        if not shopify_account:
            return {"status": "FAILED", "error": "No Shopify account configured"}
            
        shopify_service = ShopifyService(shopify_account)
        
        try:
            # Get fulfillments for this order
            fulfillments = await shopify_service.get_order_fulfillments(order.channel_order_id)
            
            stats = {
                "fulfillments_processed": 0,
                "shipments_created": 0,
                "shipments_updated": 0,
                "tracking_numbers_found": 0,
                "errors": []
            }
            
            for fulfillment in fulfillments:
                try:
                    result = await self.process_fulfillment(fulfillment, order)
                    stats["fulfillments_processed"] += 1
                    stats["shipments_created"] += result.get("created", 0)
                    stats["shipments_updated"] += result.get("updated", 0)
                    stats["tracking_numbers_found"] += result.get("tracking_found", 0)
                    
                except Exception as e:
                    error_msg = f"Error processing fulfillment {fulfillment.get('id')}: {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)
            
            return {
                "status": "SUCCESS",
                "message": f"Processed {stats['fulfillments_processed']} fulfillments for order {order_id}",
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Failed to sync fulfillments for order {order_id}: {e}")
            return {"status": "FAILED", "error": str(e)}
    
    async def sync_all_pending_orders(self, limit: int = 250) -> Dict:
        """
        Sync fulfillments for orders that don't have shipment records yet
        """
        shopify_account = self.get_shopify_account()
        if not shopify_account:
            return {"status": "FAILED", "error": "No Shopify account configured"}
        
        # Get orders that don't have order_shipments yet
        orders_without_shipments = self.db.query(Order).filter(
            Order.channel_order_id.isnot(None),
            ~Order.id.in_(
                self.db.query(OrderShipment.order_id).distinct()
            )
        ).limit(limit).all()
        
        logger.info(f"Found {len(orders_without_shipments)} orders without shipments")
        
        stats = {
            "orders_checked": 0,
            "orders_with_fulfillments": 0,
            "shipments_created": 0,
            "tracking_numbers_found": 0,
            "errors": []
        }
        
        shopify_service = ShopifyService(shopify_account)
        
        for order in orders_without_shipments:
            try:
                # Get fulfillments for this order
                fulfillments = await shopify_service.get_order_fulfillments(order.channel_order_id)
                
                if fulfillments:
                    stats["orders_with_fulfillments"] += 1
                    
                    for fulfillment in fulfillments:
                        result = await self.process_fulfillment(fulfillment, order)
                        stats["shipments_created"] += result.get("created", 0)
                        stats["tracking_numbers_found"] += result.get("tracking_found", 0)
                
                stats["orders_checked"] += 1
                
            except Exception as e:
                error_msg = f"Error processing order {order.channel_order_id}: {str(e)}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
        
        return {
            "status": "SUCCESS",
            "message": f"Checked {stats['orders_checked']} orders, created {stats['shipments_created']} shipments with {stats['tracking_numbers_found']} tracking numbers",
            "stats": stats
        }
    
    async def process_fulfillment(self, fulfillment: Dict, order: Order) -> Dict:
        """Process a single Shopify fulfillment"""
        
        fulfillment_id = str(fulfillment.get('id', ''))
        if not fulfillment_id:
            return {"created": 0, "updated": 0, "tracking_found": 0}
        
        # Extract tracking info
        tracking_info = fulfillment.get('tracking_info', [])
        if not tracking_info:
            # Fulfillment exists but no tracking info
            logger.info(f"Fulfillment {fulfillment_id} has no tracking info")
            return {"created": 0, "updated": 0, "tracking_found": 0}
        
        stats = {"created": 0, "updated": 0, "tracking_found": 0}
        
        for tracking in tracking_info:
            tracking_number = tracking.get('number', '').strip()
            courier_name = tracking.get('company', '').strip()
            
            if not tracking_number:
                continue
            
            stats["tracking_found"] += 1
            
            # Check if shipment already exists
            existing_shipment = self.db.query(OrderShipment).filter(
                OrderShipment.order_id == order.id,
                OrderShipment.shopify_fulfillment_id == fulfillment_id,
                OrderShipment.tracking_number == tracking_number
            ).first()
            
            # Map Shopify fulfillment status to our status
            fulfillment_status = fulfillment.get('status', '').lower()
            delivery_status = self.map_fulfillment_status(fulfillment_status)
            
            if existing_shipment:
                # Update existing shipment
                existing_shipment.courier = courier_name
                existing_shipment.fulfillment_status = fulfillment_status
                existing_shipment.delivery_status = delivery_status
                existing_shipment.last_synced_at = datetime.now(timezone.utc)
                
                stats["updated"] += 1
                logger.info(f"Updated shipment {tracking_number} for order {order.channel_order_id}")
                
            else:
                # Create new shipment
                shipment = OrderShipment(
                    order_id=order.id,
                    shopify_fulfillment_id=fulfillment_id,
                    tracking_number=tracking_number,
                    courier=courier_name,
                    fulfillment_status=fulfillment_status,
                    delivery_status=delivery_status,
                    last_synced_at=datetime.now(timezone.utc)
                )
                
                self.db.add(shipment)
                stats["created"] += 1
                logger.info(f"Created shipment {tracking_number} for order {order.channel_order_id}")
        
        # Commit changes for this fulfillment
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to commit shipment changes: {e}")
            raise
            
        return stats
    
    def map_fulfillment_status(self, fulfillment_status: str) -> str:
        """Map Shopify fulfillment status to delivery status"""
        status_map = {
            'success': 'DELIVERED',
            'fulfilled': 'SHIPPED',
            'in_transit': 'IN_TRANSIT',
            'out_for_delivery': 'IN_TRANSIT',
            'failure': 'RTO',
            'cancelled': 'CANCELLED',
            'pending': 'PENDING',
            'partial': 'PARTIAL',
            'restocked': 'RETURNED'
        }
        
        return status_map.get(fulfillment_status, 'PENDING')


# Convenience functions for easy usage
async def sync_order_fulfillments(db: Session, order_id: str) -> Dict:
    """Convenience function to sync fulfillments for a specific order"""
    sync_service = ShopifyFulfillmentSync(db)
    return await sync_service.sync_fulfillments_for_order(order_id)


async def sync_all_pending_fulfillments(db: Session, limit: int = 250) -> Dict:
    """Convenience function to sync all pending fulfillments"""
    sync_service = ShopifyFulfillmentSync(db)
    return await sync_service.sync_all_pending_orders(limit=limit)
