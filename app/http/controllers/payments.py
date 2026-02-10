"""
Payment gateway integration for prepaid orders settlement tracking
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Order, OrderFinance, OrderStatus
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settlements")
async def get_settlements(
    days: int = 30,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get payment gateway settlements for prepaid orders
    """
    try:
        # Query order settlements (prepaid orders)
        query = db.query(Order, OrderFinance).join(
            OrderFinance, Order.id == OrderFinance.order_id
        ).filter(
            Order.payment_mode == 'PREPAID',
            OrderFinance.settlement_status.in_(['PENDING', 'PROCESSING', 'SETTLED', 'FAILED'])
        )
        
        if status_filter:
            query = query.filter(OrderFinance.settlement_status == status_filter.upper())
        
        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(OrderFinance.settlement_date >= cutoff)
        
        settlements = query.order_by(OrderFinance.settlement_date.desc()).limit(100).all()
        
        return {
            "settlements": [
                {
                    "orderId": order.id,
                    "channelOrderId": order.channel_order_id,
                    "customerName": order.customer_name,
                    "amount": float(order.order_total),
                    "gateway": order_finance.gateway or "unknown",
                    "status": order_finance.settlement_status,
                    "expectedDate": order_finance.expected_settlement_date.isoformat() if order_finance.expected_settlement_date else None,
                    "settledDate": order_finance.settlement_date.isoformat() if order_finance.settlement_date else None,
                    "transactionId": order_finance.settlement_transaction_id,
                }
                for order, order_finance in settlements
            ],
            "summary": {
                "total": sum(float(s.amount) for s in settlements),
                "pending": sum(1 for s in settlements if s.status == 'PENDING'),
                "settled": sum(1 for s in settlements if s.status == 'SETTLED'),
                "failed": sum(1 for s in settlements if s.status == 'FAILED')
            }
        }
    except Exception as e:
        logger.exception("Failed to fetch settlements: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch settlements")


@router.post("/webhook")
async def payment_webhook(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """
    Handle payment gateway webhooks for settlement updates
    """
    try:
        # Generic webhook handler - adapt based on your payment gateway
        event_type = payload.get("event") or payload.get("type")
        order_id = payload.get("order_id") or payload.get("reference")
        
        if not order_id:
            logger.warning("Webhook missing order_id: %s", payload)
            return {"status": "ignored"}
        
        # Find order
        order = db.query(Order).filter(Order.channel_order_id == order_id).first()
        if not order:
            logger.warning("Webhook for unknown order: %s", order_id)
            return {"status": "ignored"}
        
        # Get or create finance record
        order_finance = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
        if not order_finance:
            order_finance = OrderFinance(
                order_id=order.id,
                gateway="payment_gateway",
                settlement_status="PENDING"
            )
            db.add(order_finance)
        
        # Process webhook event
        if event_type in ["payment.settled", "payment.captured", "charge.succeeded"]:
            order_finance.settlement_status = "SETTLED"
            order_finance.settlement_date = datetime.now(timezone.utc)
            order_finance.settlement_amount = Decimal(str(payload.get("amount", 0)))
            order_finance.settlement_transaction_id = payload.get("transaction_id") or payload.get("id")
        elif event_type in ["payment.failed", "charge.failed"]:
            order_finance.settlement_status = "FAILED"
            order_finance.settlement_date = datetime.now(timezone.utc)
        
        # Update order status
        if order_finance.settlement_status == "SETTLED":
            order.status = OrderStatus.DELIVERED
        elif order_finance.settlement_status == "FAILED":
            order.status = OrderStatus.PAYMENT_FAILED
        
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info("Processed webhook for order %s: status=%s", order_id, order_finance.settlement_status)
        return {"status": "processed"}
        
    except Exception as e:
        logger.exception("Webhook processing failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/reconcile")
async def reconcile_payment(
    order_id: str,
    amount: float,
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manual reconciliation for payment gateway settlement
    """
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.payment_mode != 'PREPAID':
            raise HTTPException(status_code=400, detail="Order is not prepaid")
        
        order_finance = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
        if not order_finance:
            order_finance = OrderFinance(
                order_id=order.id,
                gateway="payment_gateway",
                settlement_status="SETTLED",
                settlement_amount=Decimal(str(amount)),
                settlement_date=datetime.now(timezone.utc),
                settlement_transaction_id=transaction_id
            )
            db.add(order_finance)
        
        # Update order status
        order.status = OrderStatus.DELIVERED
        order.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        logger.info("Manually reconciled payment for order %s: amount=%s", order_id, amount)
        return {"status": "reconciled"}
        
    except Exception as e:
        logger.exception("Payment reconciliation failed: %s", e)
        raise HTTPException(status_code=500, detail="Reconciliation failed")
