"""
AWB Sync Worker - Background worker for Selloship AWB discovery
Runs every 5 minutes to automatically discover AWBs and update orders.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.selloship_service import process_awb_discovery_batch
from app.models import SelloshipMapping

logger = logging.getLogger(__name__)


async def awb_sync_worker():
    """
    Main AWB sync worker that runs continuously.
    Processes orders every 5 minutes.
    """
    logger.info("[AWB_WORKER] Starting AWB sync worker")
    
    while True:
        try:
            db = SessionLocal()
            start_time = datetime.now(timezone.utc)
            
            # Get stats before processing
            stats_before = await get_awb_sync_stats(db)
            logger.info(f"[AWB_WORKER] Starting batch - Pending: {stats_before.get('pending_count', 0)}")
            
            # Process AWB discovery
            processed, found = await process_awb_discovery_batch(db, batch_size=50)
            
            # Get stats after processing
            stats_after = await get_awb_sync_stats(db)
            
            # Log results
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"[AWB_WORKER] Batch completed: {processed} orders processed, {found} AWBs found, {duration:.2f}s")
            logger.info(f"[AWB_WORKER] Stats - Before: {stats_before.get('pending_count', 0)} pending, After: {stats_after.get('pending_count', 0)} pending")
            
            db.close()
            
            # Wait 5 minutes before next run
            await asyncio.sleep(300)  # 5 minutes
            
        except Exception as e:
            logger.error(f"[AWB_WORKER] Worker error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error


async def get_awb_sync_stats(db: Session) -> dict:
    """
    Get statistics for AWB sync debugging.
    """
    try:
        # Count pending orders (orders with Sellohip shipment but no AWB)
        from app.models import Order, OrderStatus, Shipment
        
        pending_count = db.query(Order).join(Shipment, Order.id == Shipment.order_id).filter(
            Shipment.courier_name == 'selloship',
            Shipment.awb_number.is_(None),
            Order.status.in_([OrderStatus.NEW, OrderStatus.PACKED, OrderStatus.SHIPPED])
        ).count()
        
        # Count mapped orders
        mapped_count = db.query(SelloshipMapping).filter(
            SelloshipMapping.awb.isnot(None)
        ).count()
        
        # Count total mappings
        total_mappings = db.query(SelloshipMapping).count()
        
        # Get last sync time
        last_sync = db.query(SelloshipMapping).order_by(SelloshipMapping.last_checked.desc()).first()
        last_sync_time = last_sync.last_checked if last_sync else None
        
        return {
            "pending_count": pending_count,
            "mapped_count": mapped_count,
            "total_mappings": total_mappings,
            "missing_awb": pending_count,
            "last_sync": last_sync_time.isoformat() if last_sync_time else None
        }
        
    except Exception as e:
        logger.error(f"[AWB_WORKER] Failed to get stats: {e}")
        return {
            "pending_count": 0,
            "mapped_count": 0,
            "total_mappings": 0,
            "missing_awb": 0,
            "last_sync": None,
            "error": str(e)
        }


def start_awb_sync_worker():
    """
    Start the AWB sync worker in the background.
    """
    logger.info("[AWB_WORKER] Starting background AWB sync worker")
    
    try:
        asyncio.run(awb_sync_worker())
    except KeyboardInterrupt:
        logger.info("[AWB_WORKER] Worker stopped by user")
    except Exception as e:
        logger.error(f"[AWB_WORKER] Worker crashed: {e}")
        raise


if __name__ == "__main__":
    start_awb_sync_worker()
