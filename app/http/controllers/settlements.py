"""
Settlement management endpoints - payment gateway and COD settlements
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Order, OrderFinance
from app.auth import get_current_user
from app.services.settlement_worker import daily_settlement_sync

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_settlements(
    days: int = Query(30, ge=1, le=365),
    status_filter: Optional[str] = None,
    partner_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all settlements for the user with filtering
    """
    try:
        # Build query
        query = db.query(Order, OrderFinance).join(
            OrderFinance, Order.id == OrderFinance.order_id
        ).filter(Order.user_id == current_user.id)
        
        # Apply filters
        if status_filter:
            query = query.filter(OrderFinance.settlement_status == status_filter.upper())
        
        if partner_filter:
            query = query.filter(OrderFinance.partner == partner_filter.upper())
        
        if days > 0:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(OrderFinance.settlement_date >= cutoff_date)
        
        # Order by settlement date descending
        settlements = query.order_by(OrderFinance.settlement_date.desc()).limit(200).all()
        
        # Format response
        settlement_list = []
        for order, order_finance in settlements:
            settlement_list.append({
                "id": order_finance.id,
                "orderId": order.id,
                "channelOrderId": order.channel_order_id,
                "customerName": order.customer_name,
                "amount": float(order.order_total),
                "partner": order_finance.partner,
                "status": order_finance.settlement_status,
                "expectedDate": order_finance.expected_settlement_date.isoformat() if order_finance.expected_settlement_date else None,
                "settledDate": order_finance.settlement_date.isoformat() if order_finance.settlement_date else None,
                "transactionId": order_finance.settlement_transaction_id,
                "codAmount": float(order_finance.cod_amount) if order_finance.cod_amount else 0,
                "settlementAmount": float(order_finance.settlement_amount) if order_finance.settlement_amount else 0,
                "utr": order_finance.utr,
                "overdueDays": _calculate_overdue_days(order_finance),
                "createdAt": order_finance.created_at.isoformat() if order_finance.created_at else None,
                "updatedAt": order_finance.updated_at.isoformat() if order_finance.updated_at else None
            })
        
        # Calculate summary
        summary = {
            "total": sum(float(s.amount) for s in settlement_list),
            "pending": sum(1 for s in settlement_list if s.status == 'PENDING'),
            "settled": sum(1 for s in settlement_list if s.status == 'SETTLED'),
            "overdue": sum(1 for s in settlement_list if s.overdueDays > 7),
            "cod": sum(s.codAmount for s in settlement_list),
            "gateway": sum(1 for s in settlement_list if s.partner == 'PAYMENT_GATEWAY'),
            "selloship": sum(1 for s in settlement_list if s.partner == 'COD'),
            "delhivery": sum(1 for s in settlement_list if s.partner == 'DELHIVERY')
        }
        
        return {
            "settlements": settlement_list,
            "summary": summary,
            "filters": {
                "days": days,
                "status": status_filter,
                "partner": partner_filter
            }
        }
        
    except Exception as e:
        logger.exception("Failed to fetch settlements: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch settlements")


def _calculate_overdue_days(settlement: OrderFinance) -> int:
    """Calculate overdue days for a settlement"""
    if not settlement.settlement_date:
        return 0
    
    delta = datetime.now(timezone.utc) - settlement.settlement_date
    return delta.days


@router.get("/forecast")
async def get_settlement_forecast(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get settlement forecast - expected future settlements
    """
    try:
        # Get recent orders for forecasting
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        pending_orders = db.query(Order).filter(
            Order.user_id == current_user.id,
            Order.status.in_(['NEW', 'CONFIRMED', 'PACKED', 'SHIPPED']),
            Order.payment_mode == 'COD',  # COD orders only
            Order.created_at >= cutoff_date
        ).all()
        
        # Calculate forecast
        forecast = {
            "pendingCODOrders": len(pending_orders),
            "expectedCODAmount": sum(float(order.order_total) for order in pending_orders),
            "expectedSettlementDates": [
                (order.created_at + timedelta(days=7)).strftime("%Y-%m-%d") 
                for order in pending_orders
            ],
            "partner": {
                "selloship": "Selloship",  # Assume Selloship for COD
                "delhivery": "Delhivery"  # Assume Delhivery for RTO
            }
        }
        
        return forecast
        
    except Exception as e:
        logger.exception("Failed to generate forecast: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate forecast")


@router.post("/sync")
async def trigger_settlement_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger settlement sync
    """
    try:
        result = await daily_settlement_sync()
        
        return {
            "message": "Settlement sync completed",
            "result": result
        }
        
    except Exception as e:
        logger.exception("Manual settlement sync failed: %s", e)
        raise HTTPException(status_code=500, detail="Sync failed")


@router.post("/{settlement_id}/mark-overdue")
async def mark_settlement_overdue(
    settlement_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark a settlement as overdue
    """
    try:
        from app.models import OrderFinance
        
        settlement = db.query(OrderFinance).filter(
            OrderFinance.id == settlement_id,
            OrderFinance.user_id == current_user.id
        ).first()
        
        if not settlement:
            raise HTTPException(status_code=404, detail="Settlement not found")
        
        settlement.status = 'OVERDUE'
        settlement.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info("Marked settlement as overdue: %s", settlement_id)
        
        return {
            "message": "Settlement marked as overdue",
            "settlementId": settlement_id
        }
        
    except Exception as e:
        logger.exception("Failed to mark settlement overdue: %s", e)
        raise HTTPException(status_code=500, detail="Operation failed")
