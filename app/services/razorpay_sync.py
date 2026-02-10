"""
Razorpay payment and settlement synchronization service
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.database import get_db
from app.models import Order, OrderFinance, OrderStatus
from app.services.razorpay_service import get_razorpay_service
from app.services.settlement_worker import recompute_profit_for_settled_orders

logger = logging.getLogger(__name__)


async def sync_razorpay_payments(
    db: Any,
    days_back: int = 7,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sync Razorpay payments and create order payments
    """
    razorpay_service = get_razorpay_service()
    if not razorpay_service:
        logger.warning("Razorpay service not available")
        return {"synced": 0, "errors": ["Razorpay not configured"]}
    
    try:
        # Get payments from last N days
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        payments = await razorpay_service.fetch_payments(start_date, end_date)
        synced_count = 0
        errors = []
        
        for payment in payments:
            try:
                # Extract order_id from payment description
                order_id = payment.get("order_id")
                if not order_id:
                    errors.append(f"Payment {payment.get('razorpay_payment_id')} missing order_id")
                    continue
                
                # Find order in database
                order = db.query(Order).filter(Order.channel_order_id == order_id).first()
                if not order:
                    errors.append(f"Order {order_id} not found")
                    continue
                
                # Check if payment already exists
                existing_payment = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
                if existing_payment:
                    logger.debug(f"Payment for order {order_id} already exists, skipping")
                    continue
                
                # Create order payment record
                order_payment = OrderFinance(
                    order_id=order.id,
                    partner="RAZORPAY",
                    settlement_status="SETTLED",
                    gateway_payment_id=payment.get("razorpay_payment_id"),
                    gateway="RAZORPAY",
                    gateway_order_id=payment.get("order_id"),
                    amount=Decimal(str(payment.get("amount", 0))),
                    currency=payment.get("currency", "INR"),
                    fee=Decimal(str(payment.get("fee", 0))),
                    tax=Decimal(str(payment.get("tax", 0))),
                    net_amount=Decimal(str(payment.get("amount", 0))) - Decimal(str(payment.get("fee", 0))) - Decimal(str(payment.get("tax", 0))),
                    status="PAID",
                    paid_at=datetime.fromisoformat(payment.get("captured_at")) if payment.get("captured_at") else None,
                    settled_at=datetime.fromisoformat(payment.get("processed_at")) if payment.get("processed_at") else None,
                    raw_response=payment
                )
                
                db.add(order_payment)
                synced_count += 1
                
                # Update order status if payment is captured
                if payment.get("status") == "captured":
                    order.status = OrderStatus.DELIVERED
                    order.updated_at = datetime.now(timezone.utc)
                
            except Exception as e:
                logger.error("Failed to sync Razorpay payment %s: %s", e)
                errors.append(f"Payment {payment.get('razorpay_payment_id')}: {str(e)}")
        
        # Commit all changes
        try:
            db.commit()
        except Exception as e:
            logger.error("Failed to commit Razorpay payment sync: %s", e)
            errors.append("Database commit failed")
        
        return {
            "synced": synced_count,
            "errors": errors
        }
    
    except Exception as e:
        logger.exception("Razorpay payment sync failed: %s", e)
        return {
            "synced": 0,
            "errors": [str(e)]
        }


async def sync_razorpay_settlements(
    db: Any,
    days_back: int = 7,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sync Razorpay settlements and create settlement records
    """
    razorpay_service = get_razorpay_service()
    if not razorpay_service:
        logger.warning("Razorpay service not available")
        return {"synced": 0, "errors": ["Razorpay not configured"]}
    
    try:
        # Get settlements from last N days
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        settlements = await razorpay_service.fetch_settlements(start_date, end_date)
        synced_count = 0
        errors = []
        
        for settlement in settlements:
            try:
                # Extract order_id from settlement description
                order_id = settlement.get("order_id")
                if not order_id:
                    errors.append(f"Settlement {settlement.get('razorpay_settlement_id')} missing order_id")
                    continue
                
                # Find order in database
                order = db.query(Order).filter(Order.channel_order_id == order_id).first()
                if not order:
                    errors.append(f"Order {order_id} not found")
                    continue
                
                # Check if settlement already exists
                existing_settlement = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
                if existing_settlement:
                    logger.debug(f"Settlement for order {order_id} already exists, skipping")
                    continue
                
                # Create settlement record
                settlement_amount = Decimal(str(settlement.get("amount", 0)))
                gateway_fees = Decimal(str(settlement.get("fees", 0)))
                total_deductions = gateway_fees + Decimal(str(settlement.get("tax", 0)))
                net_amount = settlement_amount - total_deductions
                
                order_settlement = OrderFinance(
                    order_id=order.id,
                    partner="RAZORPAY",
                    settlement_status="SETTLED",
                    gateway="RAZORPAY",
                    gateway_settlement_id=settlement.get("id"),
                    gateway_order_id=settlement.get("order_id"),
                    settlement_amount=settlement_amount,
                    gateway_fees=gateway_fees,
                    gateway_tax=Decimal(str(settlement.get("tax", 0))),
                    total_deductions=total_deductions,
                    net_amount=net_amount,
                    status="SETTLED",
                    settled_at=datetime.fromisoformat(settlement.get("processed_at")) if settlement.get("processed_at") else None,
                    utr=settlement.get("utr"),
                    raw_response=settlement
                )
                
                db.add(order_settlement)
                synced_count += 1
                
                # Update order status if settlement is processed
                if settlement.get("status") in ["processed", "settled"]:
                    order.status = OrderStatus.DELIVERED
                    order.updated_at = datetime.now(timezone.utc)
                
            except Exception as e:
                logger.error("Failed to sync Razorpay settlement %s: %s", e)
                errors.append(f"Settlement {settlement.get('razorpay_settlement_id')}: {str(e)}")
        
        # Commit all changes
        try:
            db.commit()
        except Exception as e:
            logger.error("Failed to commit Razorpay settlement sync: %s", e)
            errors.append("Database commit failed")
        
        # Trigger profit recompute for settled orders
        try:
            await recompute_profit_for_settled_orders(db)
        except Exception as e:
            logger.error("Failed to recompute profit for Razorpay settlements: %s", e)
        
        return {
            "synced": synced_count,
            "errors": errors
        }
    
    except Exception as e:
        logger.exception("Razorpay settlement sync failed: %s", e)
        return {
            "synced": 0,
            "errors": [str(e)]
        }


async def reconcile_razorpay_order(
    db: Any,
    order_id: str,
    amount: float,
    transaction_id: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manually reconcile a Razorpay order payment
    """
    razorpay_service = get_razorpay_service()
    if not razorpay_service:
        return {"status": "error", "message": "Razorpay not configured"}
    
    try:
        # Find order
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return {"status": "error", "message": "Order not found"}
        
        # Find existing order payment
        existing_payment = db.query(OrderFinance).filter(OrderFinance.order_id == order.id).first()
        
        # Create or update payment record
        if existing_payment:
            # Update existing record
            existing_payment.partner = "RAZORPAY"
            existing_payment.gateway = "RAZORPAY"
            existing_payment.gateway_payment_id = transaction_id
            existing_payment.amount = Decimal(str(amount))
            existing_payment.status = "PAID"
            existing_payment.paid_at = datetime.now(timezone.utc)
            existing_payment.settled_at = datetime.now(timezone.utc)
            existing_payment.updated_at = datetime.now(timezone.utc)
        else:
            # Create new payment record
            payment = await razorpay_service.fetch_payment(transaction_id)
            if not payment:
                return {"status": "error", "message": "Payment not found in Razorpay"}
            
            order_payment = OrderFinance(
                order_id=order.id,
                partner="RAZORPAY",
                settlement_status="SETTLED",
                gateway="RAZORPAY",
                gateway_payment_id=payment.get("razorpay_payment_id"),
                gateway_order_id=payment.get("order_id"),
                amount=Decimal(str(amount)),
                currency=payment.get("currency", "INR"),
                fee=Decimal(str(payment.get("fee", 0))),
                tax=Decimal(str(payment.get("tax", 0))),
                net_amount=Decimal(str(payment.get("amount", 0))) - Decimal(str(payment.get("fee", 0))) - Decimal(str(payment.get("tax", 0))),
                status="PAID",
                paid_at=datetime.fromisoformat(payment.get("captured_at")) if payment.get("captured_at") else None,
                settled_at=datetime.fromisoformat(payment.get("processed_at")) if payment.get("processed_at") else None,
                raw_response=payment
            )
            
            db.add(order_payment)
        
        # Update order status
        order.status = OrderStatus.DELIVERED
        order.updated_at = datetime.now(timezone.utc)
        
        # Commit changes
        db.commit()
        
        logger.info("Reconciled Razorpay order %s: amount=%s", amount)
        
        return {
            "status": "reconciled",
            "message": f"Order {order_id} reconciled with amount {amount}"
        }
        
    except Exception as e:
        logger.exception("Razorpay order reconciliation failed: %s", e)
        return {
            "status": "error",
            "message": f"Reconciliation failed: {str(e)}"
        }
