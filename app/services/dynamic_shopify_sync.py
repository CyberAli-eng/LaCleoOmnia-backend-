"""
Dynamic Shopify Sync Service
Fetches ALL orders from Shopify with tracking numbers and syncs shipment status
"""
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models import Order, Shipment, ShipmentStatus, ChannelAccount, Channel
from app.services.shopify import ShopifyService
from app.services.selloship_service import sync_selloship_shipments
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class DynamicShopifySync:
    """Dynamic Shopify synchronization service"""
    
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
    
    async def sync_all_orders(self, limit: int = 250) -> Dict:
        """
        Sync ALL orders from Shopify (fulfilled and unfulfilled)
        Creates shipment records with tracking numbers from fulfillments
        """
        shopify_account = self.get_shopify_account()
        if not shopify_account:
            return {"status": "FAILED", "error": "No Shopify account configured"}
        
        shopify_service = ShopifyService(shopify_account)
        
        try:
            # Get ALL orders from Shopify
            orders = await shopify_service.get_all_orders(limit=limit)
            logger.info(f"Fetched {len(orders)} orders from Shopify")
            
            stats = {
                "orders_processed": 0,
                "shipments_created": 0,
                "shipments_updated": 0,
                "tracking_numbers_found": 0,
                "selloship_shipments": 0,
                "errors": []
            }
            
            for shopify_order in orders:
                try:
                    result = await self.process_shopify_order(shopify_order, shopify_service)
                    stats["orders_processed"] += 1
                    stats["shipments_created"] += result.get("created", 0)
                    stats["shipments_updated"] += result.get("updated", 0)
                    stats["tracking_numbers_found"] += result.get("tracking_found", 0)
                    stats["selloship_shipments"] += result.get("selloship", 0)
                    
                except Exception as e:
                    error_msg = f"Error processing order {shopify_order.get('id')}: {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)
            
            # After creating shipments, sync with Selloship
            if stats["selloship_shipments"] > 0:
                logger.info(f"Syncing {stats['selloship_shipments']} Selloship shipments...")
                sync_result = await sync_selloship_shipments(self.db)
                stats["selloship_sync"] = sync_result
            
            return {
                "status": "SUCCESS",
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Shopify sync failed: {e}")
            return {"status": "FAILED", "error": str(e)}
    
    async def process_shopify_order(self, shopify_order: Dict, shopify_service: ShopifyService) -> Dict:
        """Process a single Shopify order and create/update shipments"""
        
        shopify_order_id = str(shopify_order.get('id', ''))
        if not shopify_order_id:
            return {"created": 0, "updated": 0, "tracking_found": 0, "selloship": 0}
        
        # Find order in our database
        order = self.db.query(Order).filter(Order.channel_order_id == shopify_order_id).first()
        if not order:
            logger.warning(f"Order {shopify_order_id} not found in database")
            return {"created": 0, "updated": 0, "tracking_found": 0, "selloship": 0}
        
        # Get fulfillments for this order
        fulfillments = shopify_order.get('fulfillments', [])
        if not fulfillments:
            # No fulfillments yet
            return {"created": 0, "updated": 0, "tracking_found": 0, "selloship": 0}
        
        stats = {"created": 0, "updated": 0, "tracking_found": 0, "selloship": 0}
        
        for fulfillment in fulfillments:
            tracking_info = fulfillment.get('tracking_info', [])
            if not tracking_info:
                continue
            
            for tracking in tracking_info:
                tracking_number = tracking.get('number', '').strip()
                courier_name = tracking.get('company', '').strip().lower()
                
                if not tracking_number:
                    continue
                
                stats["tracking_found"] += 1
                
                # Check if shipment already exists
                existing_shipment = self.db.query(Shipment).filter(
                    Shipment.order_id == order.id,
                    Shipment.awb_number == tracking_number
                ).first()
                
                # Determine if it's Selloship
                is_selloship = self.is_sellohip_shipment(courier_name, tracking_number)
                
                # Map fulfillment status to our ShipmentStatus
                fulfillment_status = fulfillment.get('status', '').lower()
                shipment_status = self.map_fulfillment_status(fulfillment_status)
                
                if existing_shipment:
                    # Update existing shipment
                    existing_shipment.courier_name = 'selloship' if is_selloship else courier_name
                    existing_shipment.status = shipment_status
                    existing_shipment.last_synced_at = datetime.utcnow()
                    
                    if shipment_status == ShipmentStatus.DELIVERED:
                        existing_shipment.delivered_at = datetime.utcnow()
                    
                    stats["updated"] += 1
                    logger.info(f"Updated shipment {tracking_number} for order {shopify_order_id}")
                    
                else:
                    # Create new shipment
                    shipment = Shipment(
                        order_id=order.id,
                        courier_name='selloship' if is_selloship else courier_name,
                        awb_number=tracking_number,
                        tracking_url=tracking.get('url', ''),
                        status=shipment_status,
                        shipped_at=datetime.strptime(fulfillment.get('created_at', ''), '%Y-%m-%dT%H:%M:%S%z') if fulfillment.get('created_at') else datetime.utcnow(),
                        delivered_at=datetime.utcnow() if shipment_status == ShipmentStatus.DELIVERED else None,
                        forward_cost=Decimal('50.00'),  # Default cost
                        reverse_cost=Decimal('50.00'),   # Default cost
                        last_synced_at=datetime.utcnow()
                    )
                    
                    self.db.add(shipment)
                    stats["created"] += 1
                    logger.info(f"Created shipment {tracking_number} for order {shopify_order_id}")
                
                if is_selloship:
                    stats["selloship"] += 1
        
        return stats
    
    def is_sellohip_shipment(self, courier_name: str, tracking_number: str) -> bool:
        """Determine if shipment is from Selloship"""
        courier_lower = courier_name.lower()
        tracking_lower = tracking_number.lower()
        
        # Check by courier name
        if 'selloship' in courier_lower:
            return True
        
        # Check by tracking number patterns (add your Selloship patterns)
        selloship_patterns = ['sl', 'sx', 'sel', 'ss']  # Add actual patterns
        return any(pattern in tracking_lower for pattern in selloship_patterns)
    
    def map_fulfillment_status(self, fulfillment_status: str) -> ShipmentStatus:
        """Map Shopify fulfillment status to our ShipmentStatus"""
        status_map = {
            'success': ShipmentStatus.DELIVERED,
            'fulfilled': ShipmentStatus.SHIPPED,
            'in_transit': ShipmentStatus.IN_TRANSIT,
            'out_for_delivery': ShipmentStatus.IN_TRANSIT,
            'failure': ShipmentStatus.RTO_INITIATED,
            'cancelled': ShipmentStatus.CANCELLED
        }
        
        return status_map.get(fulfillment_status, ShipmentStatus.SHIPPED)
    
    async def sync_existing_orders_with_tracking(self, limit: int = 250) -> Dict:
        """
        Sync existing orders in database that might have tracking numbers in Shopify
        This addresses orders that are already in your database but weren't properly synced
        """
        shopify_account = self.get_shopify_account()
        if not shopify_account:
            return {"status": "FAILED", "error": "No Shopify account configured"}
        
        shopify_service = ShopifyService(shopify_account)
        
        try:
            # Get orders from database that don't have shipments
            orders_without_shipments = self.db.query(Order).filter(
                Order.channel_order_id.isnot(None),
                ~Order.id.in_(
                    self.db.query(Shipment.order_id).distinct()
                )
            ).limit(limit).all()
            
            logger.info(f"Found {len(orders_without_shipments)} orders without shipments")
            
            stats = {
                "orders_checked": 0,
                "shipments_created": 0,
                "tracking_numbers_found": 0,
                "errors": []
            }
            
            for order in orders_without_shipments:
                try:
                    # Get full order data from Shopify including fulfillments
                    shopify_order = await shopify_service.get_single_order(order.channel_order_id)
                    if shopify_order:
                        result = await self.process_shopify_order(shopify_order, shopify_service)
                        stats["orders_checked"] += 1
                        stats["shipments_created"] += result.get("created", 0)
                        stats["tracking_numbers_found"] += result.get("tracking_found", 0)
                    
                except Exception as e:
                    error_msg = f"Error checking order {order.channel_order_id}: {str(e)}"
                    logger.error(error_msg)
                    stats["errors"].append(error_msg)
            
            return {
                "status": "SUCCESS",
                "message": f"Checked {stats['orders_checked']} orders, created {stats['shipments_created']} shipments with {stats['tracking_numbers_found']} tracking numbers",
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Sync existing orders failed: {e}")
            return {"status": "FAILED", "error": str(e)}

    async def sync_shipment_status(self, limit: int = 50) -> Dict:
        """
        Sync status for existing shipments
        Calls Selloship API for Selloship shipments
        """
        # Get Selloship shipments
        selloship_shipments = self.db.query(Shipment).filter(
            Shipment.courier_name.ilike('%selloship%')
        ).limit(limit).all()
        
        if not selloship_shipments:
            return {"status": "SUCCESS", "message": "No Selloship shipments to sync"}
        
        logger.info(f"Syncing status for {len(selloship_shipments)} Selloship shipments")
        
        # Call Selloship sync
        sync_result = await sync_selloship_shipments(self.db)
        
        return {
            "status": "SUCCESS",
            "shipments_synced": len(selloship_shipments),
            "sync_result": sync_result
        }

# Convenience function for easy usage
async def sync_shopify_dynamically(db: Session, limit: int = 250) -> Dict:
    """Convenience function to sync Shopify orders dynamically"""
    sync_service = DynamicShopifySync(db)
    return await sync_service.sync_all_orders(limit=limit)

async def sync_existing_orders_with_tracking(db: Session, limit: int = 250) -> Dict:
    """Convenience function to sync existing orders with tracking numbers"""
    sync_service = DynamicShopifySync(db)
    return await sync_service.sync_existing_orders_with_tracking(limit=limit)

async def sync_shipment_status_dynamically(db: Session, limit: int = 50) -> Dict:
    """Convenience function to sync shipment status dynamically"""
    sync_service = DynamicShopifySync(db)
    return await sync_service.sync_shipment_status(limit)
