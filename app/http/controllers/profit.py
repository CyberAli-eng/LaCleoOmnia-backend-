"""
Profit engine: recompute order profit (after sku_costs update or order change).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, OrderProfit, User, ChannelAccount
from app.auth import get_current_user
from app.services.profit_calculator import compute_profit_for_order

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/recompute")
async def recompute_profit(
    order_id: str | None = Query(None, description="Recompute one order; omit to recompute all for user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recompute profit for one order or all orders belonging to the current user.
    Call after updating sku_costs or when profit shows missing_costs/partial.
    """
    if order_id:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        account_ids = [a.id for a in db.query(ChannelAccount).filter(ChannelAccount.user_id == current_user.id).all()]
        if order.channel_account_id not in account_ids:
            raise HTTPException(status_code=403, detail="Access denied")
        row = compute_profit_for_order(db, order_id)
        db.commit()
        return {
            "recomputed": 1,
            "orderId": order_id,
            "profit": {
                "revenue": float(row.revenue),
                "productCost": float(row.product_cost),
                "netProfit": float(row.net_profit),
                "status": row.status,
            } if row else None,
        }
    # Recompute all orders for user's channel accounts
    account_ids = [a.id for a in db.query(ChannelAccount).filter(ChannelAccount.user_id == current_user.id).all()]
    if not account_ids:
        return {"recomputed": 0, "message": "No channel accounts"}
    orders = db.query(Order).filter(Order.channel_account_id.in_(account_ids)).all()
    count = 0
    for order in orders:
        try:
            compute_profit_for_order(db, order.id)
            count += 1
        except Exception as e:
            logger.warning("Profit recompute for order %s failed: %s", order.id, e)
    db.commit()
    return {"recomputed": count, "totalOrders": len(orders)}
