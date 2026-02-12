"""
Shipment Status Sync Worker - Background worker for Selloship status enrichment
Runs every 15 minutes to enrich shipment status from Selloship
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.selloship_status_enrichment import enrich_all_active_shipments
from app.models import OrderShipment

logger = logging.getLogger(__name__)


async def shipment_status_sync_worker():
    """
    Main shipment status sync worker that runs continuously.
    Processes shipments every 15 minutes.
    """
    logger.info("[SHIPMENT_STATUS_WORKER] Starting shipment status sync worker")
    
    while True:
        try:
            db = SessionLocal()
            start_time = datetime.now(timezone.utc)
            
            # Get stats before processing
            stats_before = await get_status_sync_stats(db)
            logger.info(f"[SHIPMENT_STATUS_WORKER] Starting batch - Active shipments: {stats_before.get('active_shipments', 0)}")
            
            # Process status enrichment
            result = await enrich_all_active_shipments(db, batch_size=50)
            
            # Get stats after processing
            stats_after = await get_status_sync_stats(db)
            
            # Log results
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"[SHIPMENT_STATUS_WORKER] Batch completed in {duration:.2f}s")
            logger.info(f"[SHIPMENT_STATUS_WORKER] Result: {result.get('message', 'No message')}")
            logger.info(f"[SHIPMENT_STATUS_WORKER] Stats - Before: {stats_before.get('active_shipments', 0)} active, After: {stats_after.get('active_shipments', 0)}")
            
            # Trigger finance recompute for status changes
            if result.get('stats', {}).get('updated', 0) > 0:
                logger.info(f"[SHIPMENT_STATUS_WORKER] {result['stats']['updated']} shipments updated, triggering finance recompute")
                await trigger_finance_recompute_for_updated_shipments(db)
            
            db.close()
            
            # Wait 15 minutes before next run
            await asyncio.sleep(900)  # 15 minutes
            
        except Exception as e:
            logger.error(f"[SHIPMENT_STATUS_WORKER] Worker error: {e}")
            await asyncio.sleep(180)  # Wait 3 minutes on error


async def get_status_sync_stats(db: Session) -> dict:
    """
    Get statistics for status sync debugging.
    """
    try:
        # Count total shipments
        total_shipments = db.query(OrderShipment).count()
        
        # Count shipments with tracking numbers
        shipments_with_tracking = db.query(OrderShipment).filter(
            OrderShipment.tracking_number.isnot(None)
        ).count()
        
        # Count active shipments (excluding final statuses)
        final_statuses = ['DELIVERED', 'RTO', 'LOST', 'CANCELLED']
        active_shipments = db.query(OrderShipment).filter(
            OrderShipment.tracking_number.isnot(None),
            ~OrderShipment.delivery_status.in_(final_statuses)
        ).count()
        
        # Count shipments by delivery status
        delivered_count = db.query(OrderShipment).filter(
            OrderShipment.delivery_status == 'DELIVERED'
        ).count()
        
        in_transit_count = db.query(OrderShipment).filter(
            OrderShipment.delivery_status == 'IN_TRANSIT'
        ).count()
        
        pending_count = db.query(OrderShipment).filter(
            OrderShipment.delivery_status == 'PENDING'
        ).count()
        
        rto_count = db.query(OrderShipment).filter(
            OrderShipment.delivery_status == 'RTO'
        ).count()
        
        # Count shipments with Selloship status
        selloship_enriched = db.query(OrderShipment).filter(
            OrderShipment.selloship_status.isnot(None)
        ).count()
        
        # Get last sync time
        last_sync = db.query(OrderShipment).order_by(OrderShipment.last_synced_at.desc()).first()
        last_sync_time = last_sync.last_synced_at if last_sync else None
        
        return {
            "total_shipments": total_shipments,
            "shipments_with_tracking": shipments_with_tracking,
            "active_shipments": active_shipments,
            "delivered_count": delivered_count,
            "in_transit_count": in_transit_count,
            "pending_count": pending_count,
            "rto_count": rto_count,
            "selloship_enriched": selloship_enriched,
            "last_sync": last_sync_time.isoformat() if last_sync_time else None
        }
        
    except Exception as e:
        logger.error(f"[SHIPMENT_STATUS_WORKER] Failed to get stats: {e}")
        return {
            "total_shipments": 0,
            "shipments_with_tracking": 0,
            "active_shipments": 0,
            "delivered_count": 0,
            "in_transit_count": 0,
            "pending_count": 0,
            "rto_count": 0,
            "selloship_enriched": 0,
            "last_sync": None,
            "error": str(e)
        }


async def trigger_finance_recompute_for_updated_shipments(db: Session):
    """
    Trigger finance recompute for shipments that were recently updated
    """
    try:
        from app.services.finance_engine import FinanceEngine
        
        # Get shipments updated in the last 5 minutes
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        recent_updates = db.query(OrderShipment).filter(
            OrderShipment.last_synced_at >= five_minutes_ago,
            OrderShipment.selloship_status.isnot(None)
        ).all()
        
        if not recent_updates:
            return
        
        finance_engine = FinanceEngine(db)
        
        for shipment in recent_updates:
            try:
                # Trigger finance recompute for the order
                await finance_engine.recompute_order_finance(shipment.order_id)
                logger.debug(f"[SHIPMENT_STATUS_WORKER] Finance recompute triggered for order {shipment.order_id}")
            except Exception as e:
                logger.error(f"[SHIPMENT_STATUS_WORKER] Failed to recompute finance for order {shipment.order_id}: {e}")
        
        logger.info(f"[SHIPMENT_STATUS_WORKER] Finance recompute triggered for {len(recent_updates)} recently updated shipments")
        
    except Exception as e:
        logger.error(f"[SHIPMENT_STATUS_WORKER] Failed to trigger finance recompute: {e}")


def start_shipment_status_sync_worker():
    """
    Start the shipment status sync worker in the background.
    """
    logger.info("[SHIPMENT_STATUS_WORKER] Starting background shipment status sync worker")
    
    try:
        asyncio.run(shipment_status_sync_worker())
    except KeyboardInterrupt:
        logger.info("[SHIPMENT_STATUS_WORKER] Worker stopped by user")
    except Exception as e:
        logger.error(f"[SHIPMENT_STATUS_WORKER] Worker crashed: {e}")
        raise


if __name__ == "__main__":
    start_shipment_status_sync_worker()
