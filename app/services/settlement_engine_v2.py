"""
Enhanced settlement engine with Razorpay integration
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.database import get_db
from app.models import Order, OrderFinance, OrderStatus
from app.services.settlement_worker import recompute_profit_for_settled_orders
from app.services.cod_settlement_sync import sync_cod_settlements
from app.services.razorpay_sync import sync_razorpay_settlements

logger = logging.getLogger(__name__)


async def create_gateway_settlement(
    db: Any,
    order_id: str,
    gateway: str,
    settlement_id: str,
    amount: Decimal,
    fees: Decimal,
    tax: Decimal,
    net_amount: Decimal,
    settled_at: Optional[datetime] = None,
    utr: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a gateway settlement record (for Razorpay, etc.)
    """
    try:
        # Find order
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return {"status": "error", "message": "Order not found"}
        
        # Create settlement record
        order_settlement = OrderFinance(
            order_id=order_id,
            partner=gateway,
            settlement_status="PENDING",
            gateway=gateway,
            gateway_settlement_id=settlement_id,
            gateway_order_id=order_id,
            settlement_amount=amount,
            gateway_fees=fees,
            gateway_tax=tax,
            total_deductions=fees + tax,
            net_amount=net_amount,
            status="PENDING",
            settled_at=settled_at,
            utr=utr,
            raw_response={"gateway": gateway, "settlement_id": settlement_id}
        )
        
        db.add(order_settlement)
        db.commit()
        
        logger.info(f"Created {gateway} settlement for order {order_id}: amount={amount}")
        
        return {
            "status": "created",
            "message": f"{gateway} settlement created for order {order_id}"
        }
        
    except Exception as e:
        logger.exception("Failed to create gateway settlement: %s", e)
        return {
            "status": "error",
            "message": f"Settlement creation failed: {str(e)}"
        }


async def update_gateway_settlement(
    db: Any,
    order_id: str,
    gateway: str,
    settlement_id: str,
    status: str,
    settled_at: Optional[datetime] = None,
    utr: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update gateway settlement status
    """
    try:
        # Find order
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return {"status": "error", "message": "Order not found"}
        
        # Find settlement record
        settlement = db.query(OrderFinance).filter(
            OrderFinance.order_id == order_id,
            OrderFinance.gateway == gateway,
            OrderFinance.gateway_settlement_id == settlement_id
        ).first()
        
        if not settlement:
            return {"status": "error", "message": "Settlement not found"}
        
        # Update settlement
        settlement.status = status
        settlement.settled_at = settled_at or datetime.now(timezone.utc)
        settlement.updated_at = datetime.now(timezone.utc)
        
        if utr:
            settlement.utr = utr
        
        db.commit()
        
        logger.info(f"Updated {gateway} settlement {settlement_id} to {status}")
        
        return {
            "status": "updated",
            "message": f"{gateway} settlement {settlement_id} updated to {status}"
        }
        
    except Exception as e:
        logger.exception("Failed to update gateway settlement: %s", e)
        return {
            "status": "error",
            "message": f"Settlement update failed: {str(e)}"
        }


async def process_settlements():
    """
    Process all pending settlements (COD, Razorpay, etc.)
    """
    from app.database import get_db
    from app.models import OrderFinance, OrderStatus
    
    db = get_db()
    
    try:
        # Find pending settlements
        pending_settlements = db.query(OrderFinance).filter(
            OrderFinance.settlement_status == "PENDING"
        ).all()
        
        for settlement in pending_settlements:
            try:
                # Check if this is a gateway settlement
                if settlement.gateway in ["RAZORPAY", "PAYMENT_GATEWAY"]:
                    await process_gateway_settlement(
                        db, settlement.order_id, settlement.gateway, 
                        settlement.gateway_settlement_id, settlement.settlement_amount,
                        "SETTLED", settlement.settled_at
                    )
                # Check if this is a COD settlement
                elif settlement.partner in ["COD", "SELLOSHIP", "DELHIVERY"]:
                    # Process COD remittance
                    pass  # COD processing logic here
                    
            except Exception as e:
                logger.error("Failed to process settlement %s: %s", e)
        
        db.commit()
        
        logger.info("Settlement processing completed")
        
    except Exception as e:
        logger.exception("Settlement processing failed: %s", e)


async def get_settlement_summary(
    db: Any,
    days_back: int = 30,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get comprehensive settlement summary including all providers
    """
    from app.database import get_db
    from app.models import OrderFinance
    
    db = get_db()
    
    try:
        # Get date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        # Query all settlements in date range
        settlements = db.query(OrderFinance).filter(
            OrderFinance.settlement_date >= start_date,
            OrderFinance.settlement_date <= end_date
        ).all()
        
        # Calculate summary
        total_amount = Decimal("0")
        total_fees = Decimal("0")
        total_tax = Decimal("0")
        gateway_total = Decimal("0")
        cod_total = Decimal("0")
        selloship_total = Decimal("0")
        delhivery_total = Decimal("0")
        
        pending_count = 0
        settled_count = 0
        failed_count = 0
        overdue_count = 0
        
        for settlement in settlements:
            total_amount += settlement.settlement_amount or Decimal("0")
            total_fees += settlement.gateway_fees or Decimal("0")
            total_tax += settlement.gateway_tax or Decimal("0")
            
            if settlement.status == "PENDING":
                pending_count += 1
            elif settlement.status == "SETTLED":
                settled_count += 1
            elif settlement.status == "FAILED":
                failed_count += 1
            elif settlement.status == "OVERDUE":
                overdue_count += 1
            
            # Provider breakdown
            if settlement.gateway == "RAZORPAY":
                gateway_total += settlement.net_amount
            elif settlement.gateway == "PAYMENT_GATEWAY":
                gateway_total += settlement.net_amount
            elif settlement.partner == "COD":
                cod_total += settlement.net_amount
            elif settlement.partner == "SELLOSHIP":
                selloship_total += settlement.net_amount
            elif settlement.partner == "DELHIVERY":
                delhivery_total += settlement.net_amount
        
        return {
            "summary": {
                "total_amount": float(total_amount),
                "total_fees": float(total_fees),
                "total_tax": float(total_tax),
                "net_amount": float(total_amount - total_fees - total_tax),
                "pending_count": pending_count,
                "settled_count": settled_count,
                "failed_count": failed_count,
                "overdue_count": overdue_count,
                "total_settlements": len(settlements)
            },
            "breakdown": {
                "gateway": {
                    "total": float(gateway_total),
                    "count": len([s for s in settlements if s.gateway == "RAZORPAY"]),
                    "amount": float(gateway_total)
                },
                "payment_gateway": {
                    "total": float(gateway_total),
                    "count": len([s for s in settlements if s.gateway == "PAYMENT_GATEWAY"]),
                    "amount": float(gateway_total)
                },
                "cod": {
                    "total": float(cod_total),
                    "count": len([s for s in settlements if s.partner == "COD"]),
                    "amount": float(cod_total)
                },
                "selloship": {
                    "total": float(selloship_total),
                    "count": len([s for s in settlements if s.partner == "SELLOSHIP"]),
                    "amount": float(selloship_total)
                },
                "delhivery": {
                    "total": float(delhivery_total),
                    "count": len([s for s in settlements if s.partner == "DELHIVERY"]),
                    "amount": float(delhivery_total)
                }
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get settlement summary: %s", e)
        return {
            "summary": {},
            "error": str(e)
        }
