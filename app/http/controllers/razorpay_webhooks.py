"""
Razorpay webhook handlers for payment and settlement events
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, OrderFinance, OrderStatus
from app.services.razorpay_service import get_razorpay_service
from app.services.razorpay_sync import sync_razorpay_payments, sync_razorpay_settlements
from app.services.settlement_worker import recompute_profit_for_settled_orders
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/razorpay")
async def handle_razorpay_webhook(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    signature: str = None,
    secret: str = None
):
    """
    Handle Razorpay webhooks for payment and settlement events
    """
    razorpay_service = get_razorpay_service()
    if not razorpay_service:
        logger.warning("Razorpay service not available")
        raise HTTPException(status_code=400, detail="Razorpay not configured")
    
    # Get signature from header
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")
    
    # Verify webhook signature
    if not razorpay_service.verify_webhook_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Get event type
    event_type = payload.get("event", "")
    
    try:
        if event_type == "payment.captured":
            await handle_payment_captured(payload, db, razorpay_service)
        elif event_type == "settlement.processed":
            await handle_settlement_processed(payload, db, razorpay_service)
        elif event_type == "payout.processed":
            await handle_payout_processed(payload, db, razorpay_service)
        else:
            logger.warning(f"Unhandled Razorpay webhook event: {event_type}")
            logger.debug(f"Webhook payload: {payload}")
            
    except Exception as e:
        logger.exception("Razorpay webhook processing failed: %s", e)
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    
    return {"status": "processed"}


async def handle_payment_captured(
    payload: Dict[str, Any],
    db: Session,
    razorpay_service: RazorpayService
) -> None:
    """
    Handle Razorpay payment.captured webhook event
    """
    payment_id = payload.get("payment_id")
    order_id = payload.get("order_id")
    amount = payload.get("amount", 0)
    currency = payload.get("currency", "INR")
    
    if not all([payment_id, order_id]):
        logger.error("Missing payment_id or order_id in payment.captured webhook")
        return
    
    # Find order
    order = db.query(Order).filter(Order.channel_order_id == order_id).first()
    if not order:
        logger.error(f"Order {order_id} not found for payment {payment_id}")
        return
    
    # Check if payment already exists
    existing_payment = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
    if existing_payment:
        logger.debug(f"Payment {payment_id} for order {order_id} already exists")
        return
    
    # Create order payment record
    order_payment = OrderFinance(
        order_id=order.id,
        partner="RAZORPAY",
        settlement_status="SETTLED",
        gateway="RAZORPAY",
        gateway_payment_id=payment_id,
        gateway_order_id=order_id,
        amount=Decimal(str(amount)),
        currency=currency,
        fee=Decimal(str(payload.get("fee", 0))),
        tax=Decimal(str(payload.get("tax", 0))),
        net_amount=Decimal(str(amount)) - Decimal(str(payload.get("fee", 0))) - Decimal(str(payload.get("tax", 0))),
        status="PAID",
        paid_at=datetime.fromisoformat(payload.get("created_at")) if payload.get("created_at") else None,
        settled_at=datetime.fromisoformat(payload.get("processed_at")) if payload.get("processed_at") else None,
        raw_response=payload
    )
    
    db.add(order_payment)
    
    # Update order status
    order.status = OrderStatus.DELIVERED
    order.updated_at = datetime.now(timezone.utc)
    
    # Commit changes
    db.commit()
    
    # Trigger profit recompute
    try:
        await recompute_profit_for_settled_orders(db)
    except Exception as e:
        logger.error("Failed to recompute profit for Razorpay payment: %s", e)
    
    logger.info(f"Razorpay payment captured: order_id={order_id}, amount={amount}, payment_id={payment_id}")


async def handle_settlement_processed(
    payload: Dict[str, Any],
    db: Session,
    razorpay_service: RazorpayService
) -> None:
    """
    Handle Razorpay settlement.processed webhook event
    """
    settlement_id = payload.get("settlement_id")
    order_id = payload.get("order_id")
    amount = payload.get("amount", 0)
    currency = payload.get("currency", "INR")
    
    if not all([settlement_id, order_id]):
        logger.error("Missing settlement_id or order_id in settlement.processed webhook")
        return
    
    # Find order
    order = db.query(Order).filter(Order.channel_order_id == order_id).first()
    if not order:
        logger.error(f"Order {order_id} not found for settlement {settlement_id}")
        return
    
    # Check if settlement already exists
    existing_settlement = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
    if existing_settlement:
        logger.debug(f"Settlement {settlement_id} for order {order_id} already exists")
        return
    
    # Create settlement record
    settlement_amount = Decimal(str(amount))
    gateway_fees = Decimal(str(payload.get("fees", 0)))
    total_deductions = gateway_fees + Decimal(str(payload.get("tax", 0)))
    net_amount = settlement_amount - total_deductions
    
    order_settlement = OrderFinance(
        order_id=order.id,
        partner="RAZORPAY",
        settlement_status="SETTLED",
        gateway="RAZORPAY",
        gateway_settlement_id=settlement_id,
        gateway_order_id=order_id,
        settlement_amount=settlement_amount,
        gateway_fees=gateway_fees,
        gateway_tax=Decimal(str(payload.get("tax", 0))),
        total_deductions=total_deductions,
        net_amount=net_amount,
        status="SETTLED",
        settled_at=datetime.fromisoformat(payload.get("processed_at")) if payload.get("processed_at") else None,
        utr=payload.get("utr"),
        raw_response=payload
    )
    
    db.add(order_settlement)
    
    # Update order status
    order.status = OrderStatus.DELIVERED
    order.updated_at = datetime.now(timezone.utc)
    
    # Commit changes
    db.commit()
    
    # Trigger profit recompute
    try:
        await recompute_profit_for_settled_orders(db)
    except Exception as e:
        logger.error("Failed to recompute profit for Razorpay settlement: %s", e)
    
    logger.info(f"Razorpay settlement processed: order_id={order_id}, amount={amount}, settlement_id={settlement_id}")


async def handle_payout_processed(
    payload: Dict[str, Any],
    db: Session,
    razorpay_service: RazorpayService
) -> None:
    """
    Handle Razorpay payout.processed webhook event (bank transfer confirmation)
    """
    settlement_id = payload.get("settlement_id")
    order_id = payload.get("order_id")
    amount = payload.get("amount", 0)
    
    if not all([settlement_id, order_id]):
        logger.error("Missing settlement_id or order_id in payout.processed webhook")
        return
    
    # Find order
    order = db.query(Order).filter(Order.channel_order_id == order_id).first()
    if not order:
        logger.error(f"Order {order_id} not found for payout {settlement_id}")
        return
    
    # Find settlement record
    settlement = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
    if not settlement:
        logger.error(f"Settlement {settlement_id} not found for order {order_id}")
        return
    
    # Update settlement record with bank confirmation
    settlement.status = "BANK_CREDITED"
    settlement.settled_at = datetime.now(timezone.utc)
    settlement.updated_at = datetime.now(timezone.utc)
    
    # Add bank transfer info if available
    if "bank_account" in payload:
        settlement.bank_account = payload.get("bank_account")
        settlement.bank_reference = payload.get("bank_reference")
    
    # Commit changes
    db.commit()
    
    logger.info(f"Razorpay payout processed: order_id={order_id}, amount={amount}, settlement_id={settlement_id}")
