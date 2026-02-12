"""
Shopify Fulfillment Worker - Background worker for Shopify fulfillment sync
Runs every 10 minutes to automatically fetch fulfillments and tracking numbers.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.shopify_fulfillment_sync import sync_all_pending_fulfillments
from app.models import OrderShipment

logger = logging.getLogger(__name__)


async def shopify_fulfillment_worker():
    """
    Main Shopify fulfillment worker that runs continuously.
    Processes orders every 10 minutes.
    """
    logger.info("[SHOPIFY_FULFILLMENT_WORKER] Starting Shopify fulfillment worker")
    
    while True:
        try:
            db = SessionLocal()
            start_time = datetime.now(timezone.utc)
            
            # Get stats before processing
            stats_before = await get_fulfillment_sync_stats(db)
            logger.info(f"[SHOPIFY_FULFILLMENT_WORKER] Starting batch - Orders without shipments: {stats_before.get('orders_without_shipments', 0)}")
            
            # Process fulfillment sync
            result = await sync_all_pending_fulfillments(db, batch_size=100)
            
            # Get stats after processing
            stats_after = await get_fulfillment_sync_stats(db)
            
            # Log results
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"[SHOPIFY_FULFILLMENT_WORKER] Batch completed in {duration:.2f}s")
            logger.info(f"[SHOPIFY_FULFILLMENT_WORKER] Result: {result.get('message', 'No message')}")
            logger.info(f"[SHOPIFY_FULFILLMENT_WORKER] Stats - Before: {stats_before.get('orders_without_shipments', 0)} orders without shipments, After: {stats_after.get('orders_without_shipments', 0)}")
            
            db.close()
            
            # Wait 10 minutes before next run
            await asyncio.sleep(600)  # 10 minutes
            
        except Exception as e:
            logger.error(f"[SHOPIFY_FULFILLMENT_WORKER] Worker error: {e}")
            await asyncio.sleep(120)  # Wait 2 minutes on error


async def get_fulfillment_sync_stats(db: Session) -> dict:
    """
    Get statistics for fulfillment sync debugging.
    """
    try:
        from app.models import Order
        
        # Count orders without shipments
        orders_without_shipments = db.query(Order).filter(
            Order.channel_order_id.isnot(None),
            ~Order.id.in_(
                db.query(OrderShipment.order_id).distinct()
            )
        ).count()
        
        # Count total shipments
        total_shipments = db.query(OrderShipment).count()
        
        # Count shipments with tracking numbers
        shipments_with_tracking = db.query(OrderShipment).filter(
            OrderShipment.tracking_number.isnot(None)
        ).count()
        
        # Count shipments by status
        shipped_count = db.query(OrderShipment).filter(
            OrderShipment.fulfillment_status == 'fulfilled'
        ).count()
        
        delivered_count = db.query(OrderShipment).filter(
            OrderShipment.delivery_status == 'DELIVERED'
        ).count()
        
        # Get last sync time
        last_sync = db.query(OrderShipment).order_by(OrderShipment.last_synced_at.desc()).first()
        last_sync_time = last_sync.last_synced_at if last_sync else None
        
        return {
            "orders_without_shipments": orders_without_shipments,
            "total_shipments": total_shipments,
            "shipments_with_tracking": shipments_with_tracking,
            "shipped_count": shipped_count,
            "delivered_count": delivered_count,
            "last_sync": last_sync_time.isoformat() if last_sync_time else None
        }
        
    except Exception as e:
        logger.error(f"[SHOPIFY_FULFILLMENT_WORKER] Failed to get stats: {e}")
        return {
            "orders_without_shipments": 0,
            "total_shipments": 0,
            "shipments_with_tracking": 0,
            "shipped_count": 0,
            "delivered_count": 0,
            "last_sync": None,
            "error": str(e)
        }


def start_shopify_fulfillment_worker():
    """
    Start the Shopify fulfillment worker in the background.
    """
    logger.info("[SHOPIFY_FULFILLMENT_WORKER] Starting background Shopify fulfillment worker")
    
    try:
        asyncio.run(shopify_fulfillment_worker())
    except KeyboardInterrupt:
        logger.info("[SHOPIFY_FULFILLMENT_WORKER] Worker stopped by user")
    except Exception as e:
        logger.error(f"[SHOPIFY_FULFILLMENT_WORKER] Worker crashed: {e}")
        raise


if __name__ == "__main__":
    start_shopify_fulfillment_worker()
