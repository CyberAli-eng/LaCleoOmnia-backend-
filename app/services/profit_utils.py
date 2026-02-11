"""
Profit calculation utilities for settlement processing
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.models import OrderFinance, Order

logger = logging.getLogger(__name__)


async def recompute_profit_for_settled_orders(db: Session):
    """
    Recompute profit for orders that were recently settled
    """
    from app.services.profit_calculator import compute_profit_for_order
    from sqlalchemy import func
    
    # Find orders settled in last 24 hours
    recent_date = datetime.now(timezone.utc) - timedelta(hours=24)
    
    recently_settled = db.query(OrderFinance).filter(
        OrderFinance.settlement_status == 'SETTLED',
        OrderFinance.settlement_date >= recent_date
    ).all()
    
    for settlement in recently_settled:
        try:
            await compute_profit_for_order(db, settlement.order_id)
            logger.debug("Recomputed profit for settled order: %s", settlement.order_id)
        except Exception as e:
            logger.error("Failed to recompute profit for order %s: %s", settlement.order_id, e)
