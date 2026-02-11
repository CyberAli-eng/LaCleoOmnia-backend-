"""
Settlement automation worker - daily sync of payment and COD settlements
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.database import SessionLocal
from app.services.cod_settlement_sync import sync_cod_settlements
from app.services.razorpay_sync import sync_razorpay_payments, sync_razorpay_settlements
from app.services.settlement_engine_v2 import process_settlements

logger = logging.getLogger(__name__)


async def daily_settlement_sync():
    """
    Daily settlement worker - runs at 2 AM IST
    Syncs:
    - Payment gateway settlements (Razorpay)
    - COD remittances (Selloship + Delhivery)
    - Updates overdue settlements
    - Triggers profit recompute
    """
    IST = timezone(timedelta(hours=5, minutes=30))
    
    try:
        db = SessionLocal()
        
        logger.info("Starting daily settlement sync")
        
        # Sync Razorpay payments
        razorpay_result = await sync_razorpay_payments(db, days_back=7)
        logger.info("Razorpay payment sync: %s payments, %s errors", razorpay_result["synced"], razorpay_result["errors"])
        
        # Sync Razorpay settlements
        razorpay_settlements_result = await sync_razorpay_settlements(db, days_back=7)
        logger.info("Razorpay settlement sync: %s settlements, %s errors", razorpay_settlements_result["synced"], razorpay_settlements_result["errors"])
        
        # Sync COD settlements (existing logic)
        cod_result = await sync_cod_settlements(db, days_back=7)
        logger.info("COD settlement sync: %s settlements, %s errors", cod_result["synced"], cod_result["errors"])
        
        # Process all pending settlements
        await process_settlements()
        
        db.close()
        logger.info("Daily settlement sync completed")
        
    except Exception as e:
        logger.exception("Daily settlement sync failed: %s", e)


async def check_overdue_settlements(db: Session):
    """
    Check for overdue settlements and mark them
    """
    from app.models import OrderFinance, Order
    from sqlalchemy import func
    
    # Check for settlements older than 7 days that are still pending
    overdue_date = datetime.now(timezone.utc) - timedelta(days=7)
    
    overdue_settlements = db.query(OrderFinance).filter(
        OrderFinance.settlement_status == 'PENDING',
        OrderFinance.settlement_date < overdue_date
    ).all()
    
    for settlement in overdue_settlements:
        settlement.status = 'OVERDUE'
        settlement.updated_at = datetime.now(timezone.utc)
        logger.warning("Marking settlement as overdue: order_id=%s", settlement.order_id)
    
    if overdue_settlements:
        db.commit()
        logger.info("Marked %s settlements as overdue", len(overdue_settlements))


def start_settlement_worker():
    """
    Start the settlement worker - should be called from main.py
    """
    logger.info("Starting settlement worker service")
    
    # Schedule daily sync at 2 AM IST
    import asyncio
    
    async def run_daily_sync():
        while True:
            now_ist = datetime.now(IST)
            
            # Calculate seconds until 2 AM IST tomorrow
            tomorrow_2am = now_ist.replace(hour=2, minute=0, second=0, microsecond=0)
            if tomorrow_2am <= now_ist:
                tomorrow_2am += timedelta(days=1)
            
            seconds_until_2am = (tomorrow_2am - now_ist).total_seconds()
            
            # Sleep until 2 AM IST
            await asyncio.sleep(seconds_until_2am)
            
            # Run daily sync
            await daily_settlement_sync()
    
    # Start the background task
    asyncio.create_task(run_daily_sync())
