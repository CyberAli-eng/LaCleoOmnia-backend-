"""
Order Finance Engine - Comprehensive financial ledger for orders
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Order, OrderFinance, OrderExpense, OrderSettlement, CustomerRisk,
    OrderItem, Shipment, SkuCost, OrderShipment,
    PaymentType, FulfilmentStatus, ProfitStatus, ExpenseType, ExpenseSource, SettlementStatus, RiskTag,
    ExpenseRule, ExpenseRuleValueType
)
from app.services.credentials import decrypt_token
import json

logger = logging.getLogger(__name__)


class FinanceEngine:
    """Finance Engine with Shopify-centric shipment status integration"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def recompute_order_finance(self, order_id: str) -> Dict:
        """
        Recompute finance for an order based on current shipment status
        """
        try:
            finance = compute_order_finance(self.db, order_id)
            return {
                "status": "SUCCESS",
                "order_id": order_id,
                "fulfilment_status": finance.fulfilment_status.value,
                "profit_status": finance.profit_status.value,
                "net_profit": float(finance.net_profit),
                "revenue_realized": float(finance.revenue_realized)
            }
        except Exception as e:
            logger.error(f"Failed to recompute finance for order {order_id}: {e}")
            return {
                "status": "FAILED",
                "order_id": order_id,
                "error": str(e)
            }
    
    async def recompute_finance_for_shipment_status_change(self, shipment_id: str) -> Dict:
        """
        Trigger finance recompute when shipment status changes
        """
        shipment = self.db.query(OrderShipment).filter(OrderShipment.id == shipment_id).first()
        if not shipment:
            return {"status": "FAILED", "error": f"Shipment {shipment_id} not found"}
        
        return await self.recompute_order_finance(shipment.order_id)
    
    async def finalize_profit_on_delivery(self, shipment_id: str) -> Dict:
        """
        Finalize profit when order is delivered
        """
        shipment = self.db.query(OrderShipment).filter(OrderShipment.id == shipment_id).first()
        if not shipment:
            return {"status": "FAILED", "error": f"Shipment {shipment_id} not found"}
        
        if shipment.delivery_status != 'DELIVERED':
            return {"status": "FAILED", "error": f"Shipment {shipment_id} is not delivered"}
        
        result = await self.recompute_order_finance(shipment.order_id)
        
        if result.get("status") == "SUCCESS":
            logger.info(f"Profit finalized for delivered order {shipment.order_id}: {result.get('net_profit', 0)}")
        
        return result
    
    async def book_loss_on_rto(self, shipment_id: str) -> Dict:
        """
        Book loss when order is RTO
        """
        shipment = self.db.query(OrderShipment).filter(OrderShipment.id == shipment_id).first()
        if not shipment:
            return {"status": "FAILED", "error": f"Shipment {shipment_id} not found"}
        
        if shipment.delivery_status not in ['RTO', 'RTO_INITIATED', 'RTO_DONE']:
            return {"status": "FAILED", "error": f"Shipment {shipment_id} is not RTO"}
        
        result = await self.recompute_order_finance(shipment.order_id)
        
        if result.get("status") == "SUCCESS":
            logger.info(f"Loss booked for RTO order {shipment.order_id}: {result.get('net_profit', 0)}")
        
        return result


def compute_order_finance(db: Session, order_id: str) -> OrderFinance:
    """
    Compute complete financial ledger for an order.
    Creates/updates OrderFinance, OrderExpense, OrderSettlement records.
    """
    logger.info(f"Computing finance for order {order_id}")
    
    # Load order with related data
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")
    
    # Determine payment type and fulfilment status
    payment_type = _determine_payment_type(order)
    fulfilment_status = _determine_fulfilment_status(db, order)
    
    # Calculate revenue based on PRD rules
    revenue_realized = _calculate_revenue(order, payment_type, fulfilment_status)
    
    # Get or create OrderFinance record
    finance = db.query(OrderFinance).filter(OrderFinance.order_id == order_id).first()
    if not finance:
        logger.info(f"Creating new OrderFinance for order {order_id}")
        finance = OrderFinance(
            order_id=order_id,
            payment_type=payment_type,
            fulfilment_status=fulfilment_status
        )
        db.add(finance)
        db.flush()
        logger.info(f"Created OrderFinance: id={finance.id}, profit_status={finance.profit_status}")
    else:
        logger.info(f"Found existing OrderFinance: id={finance.id}, profit_status={finance.profit_status}")
    
    # Update finance fields
    finance.order_value = Decimal(str(order.total_amount or 0))
    finance.revenue_realized = revenue_realized
    
    # Compute and save expenses
    expenses = _compute_order_expenses(db, order, finance.id)
    total_expense = sum(exp.amount for exp in expenses)
    finance.total_expense = total_expense
    
    # Calculate profit
    net_profit = revenue_realized - total_expense
    finance.net_profit = net_profit
    
    # Debug: Check profit status assignment
    profit_status_value = ProfitStatus.PROFIT if net_profit > 0 else ProfitStatus.LOSS
    logger.info(f"Profit calculation: net_profit={net_profit}, profit_status={profit_status_value}, profit_status.value={profit_status_value.value}")
    finance.profit_status = profit_status_value
    
    # Create settlements
    _create_order_settlements(db, order, finance.id)
    
    # Update customer risk
    _update_customer_risk(db, order, fulfilment_status, net_profit)
    
    db.commit()
    logger.info(f"Finance computed for order {order_id}: revenue={revenue_realized}, expenses={total_expense}, profit={net_profit}")
    
    return finance


def _determine_payment_type(order: Order) -> PaymentType:
    """Determine payment type from order data"""
    if hasattr(order, 'payment_mode') and order.payment_mode:
        if order.payment_mode.value.upper() == 'PREPAID':
            return PaymentType.PREPAID
        elif order.payment_mode.value.upper() == 'COD':
            return PaymentType.COD
    
    # Default based on order data or assume PREPAID
    return PaymentType.PREPAID


def _determine_fulfilment_status(db: Session, order: Order) -> FulfilmentStatus:
    """Determine fulfilment status from OrderShipment data (Shopify-centric)"""
    from app.models import OrderShipment
    
    # Check OrderShipment table first (new Shopify-centric approach)
    shipments = db.query(OrderShipment).filter(OrderShipment.order_id == order.id).all()
    
    if shipments:
        # Use the most recent shipment's delivery status
        latest_shipment = max(shipments, key=lambda s: s.updated_at or s.created_at)
        delivery_status = latest_shipment.delivery_status
        
        if delivery_status:
            status = delivery_status.upper()
            if status == 'DELIVERED':
                return FulfilmentStatus.DELIVERED
            elif status in ['RTO', 'RTO_INITIATED', 'RTO_DONE']:
                return FulfilmentStatus.RTO
            elif status == 'CANCELLED':
                return FulfilmentStatus.CANCELLED
            elif status in ['IN_TRANSIT', 'SHIPPED']:
                return FulfilmentStatus.IN_TRANSIT
    
    # Fallback to legacy order status for backward compatibility
    if hasattr(order, 'status') and order.status:
        status = order.status.value.upper()
        if status == 'DELIVERED':
            return FulfilmentStatus.DELIVERED
        elif status == 'RTO' or status == 'RETURNED':
            return FulfilmentStatus.RTO
        elif status == 'CANCELLED':
            return FulfilmentStatus.CANCELLED
        elif status == 'SHIPPED':
            return FulfilmentStatus.IN_TRANSIT
    
    # Default based on order progression
    if hasattr(order, 'shipped_at') and order.shipped_at:
        return FulfilmentStatus.IN_TRANSIT
    elif hasattr(order, 'delivered_at') and order.delivered_at:
        return FulfilmentStatus.DELIVERED
    
    return FulfilmentStatus.IN_TRANSIT


def _calculate_revenue(order: Order, payment_type: PaymentType, fulfilment_status: FulfilmentStatus) -> Decimal:
    """
    Calculate realized revenue based on PRD rules:
    - PREPAID + DELIVERED = full order value
    - COD + DELIVERED = full order value  
    - Other cases = 0 revenue
    """
    if fulfilment_status == FulfilmentStatus.DELIVERED:
        return Decimal(str(order.total_amount or 0))
    
    return Decimal("0")


def _compute_order_expenses(db: Session, order: Order, finance_id: str) -> List[OrderExpense]:
    """Compute all expenses for an order"""
    expenses: List[OrderExpense] = []
    effective_date = order.created_at.date() if order.created_at else date.today()
    
    # Preserve manual expenses; recompute only SYSTEM/API rows.
    existing_manual = (
        db.query(OrderExpense)
        .filter(
            OrderExpense.order_finance_id == finance_id,
            OrderExpense.source == ExpenseSource.MANUAL,
        )
        .all()
    )
    db.query(OrderExpense).filter(
        OrderExpense.order_finance_id == finance_id,
        OrderExpense.source != ExpenseSource.MANUAL,
    ).delete()
    
    # 1. Product costs (COGS)
    product_cost = _calculate_product_costs(db, order)
    if product_cost > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.FIXED,
            source=ExpenseSource.SYSTEM,
            amount=product_cost,
            effective_date=effective_date,
            editable=False,
            description="Cost of Goods Sold"
        ))
    
    # 2. Shipping costs
    shipping_cost = _calculate_shipping_costs(db, order)
    if shipping_cost > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.FWD_SHIP,
            source=ExpenseSource.SYSTEM,
            amount=shipping_cost,
            effective_date=effective_date,
            editable=False,
            description="Forward Shipping Cost"
        ))
    
    # 3. Payment gateway fees
    gateway_fee = _calculate_gateway_fees(db, order)
    if gateway_fee > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.GATEWAY,
            source=ExpenseSource.SYSTEM,
            amount=gateway_fee,
            effective_date=effective_date,
            editable=False,
            description="Payment Gateway Fee"
        ))
    
    # 4. COD fees (if applicable)
    cod_fee = _calculate_cod_fees(db, order)
    if cod_fee > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.COD_FEE,
            source=ExpenseSource.SYSTEM,
            amount=cod_fee,
            effective_date=effective_date,
            editable=False,
            description="COD Processing Fee"
        ))
    
    # 4b. Packaging fee (optional rule-based fee)
    packaging_fee = _calculate_packaging_fee(db, order)
    if packaging_fee > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.OVERHEAD,
            source=ExpenseSource.SYSTEM,
            amount=packaging_fee,
            effective_date=effective_date,
            editable=False,
            description="Packaging Fee"
        ))

    # 5. Ad spend (blended CAC)
    ad_spend = _calculate_ad_spend(db, order)
    if ad_spend > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.ADS,
            source=ExpenseSource.SYSTEM,
            amount=ad_spend,
            effective_date=effective_date,
            editable=False,
            description="Marketing Cost (CAC)"
        ))
    
    # 6. RTO losses
    rto_loss = _calculate_rto_loss(db, order)
    if rto_loss > 0:
        expenses.append(OrderExpense(
            order_id=order.id,
            order_finance_id=finance_id,
            type=ExpenseType.REV_SHIP,
            source=ExpenseSource.SYSTEM,
            amount=rto_loss,
            effective_date=effective_date,
            editable=False,
            description="RTO Loss"
        ))
    
    # Save all expenses
    for expense in expenses:
        db.add(expense)
    
    db.flush()
    return existing_manual + expenses


def _calculate_product_costs(db: Session, order: Order) -> Decimal:
    """Calculate total product cost from SKU costs"""
    total_cost = Decimal("0")
    
    if not order.items:
        return total_cost
    
    for item in order.items:
        sku_cost = db.query(SkuCost).filter(SkuCost.sku == item.sku).first()
        if sku_cost:
            unit_cost = (
                Decimal(str(sku_cost.product_cost or 0)) +
                Decimal(str(sku_cost.packaging_cost or 0)) +
                Decimal(str(sku_cost.box_cost or 0)) +
                Decimal(str(sku_cost.inbound_cost or 0))
            )
            total_cost += unit_cost * Decimal(str(item.quantity or 1))
    
    return total_cost


def _calculate_shipping_costs(db: Session, order: Order) -> Decimal:
    """Calculate shipping costs from shipment data"""
    shipment = db.query(Shipment).filter(Shipment.order_id == order.id).first()
    if shipment:
        return Decimal(str(shipment.forward_cost or 0)) + Decimal(str(shipment.reverse_cost or 0))
    return Decimal("0")


def _get_applicable_expense_rule(
    db: Session,
    *,
    user_id: str,
    rule_type: str,
    on_date: date,
    platform: Optional[str] = None,
) -> Optional[ExpenseRule]:
    """
    Find the rule applicable on `on_date` (inclusive) for a user, optionally scoped to platform.
    Prefers platform-specific rule over generic.
    """
    q = db.query(ExpenseRule).filter(
        ExpenseRule.user_id == user_id,
        ExpenseRule.type == rule_type,
        ExpenseRule.effective_from <= on_date,
        func.coalesce(ExpenseRule.effective_to, on_date) >= on_date,
    )
    # Prefer platform-specific
    if platform:
        rule = q.filter(ExpenseRule.platform == platform).order_by(ExpenseRule.effective_from.desc()).first()
        if rule:
            return rule
    return q.filter(ExpenseRule.platform.is_(None)).order_by(ExpenseRule.effective_from.desc()).first()


def _rule_to_amount(rule: ExpenseRule, base_amount: Decimal) -> Decimal:
    """Convert a rule to an amount based on FIXED or PERCENT."""
    val = Decimal(str(rule.value or 0))
    if rule.value_type == ExpenseRuleValueType.FIXED:
        return val
    # PERCENT
    return (base_amount * val / Decimal("100")).quantize(Decimal("0.01"))


def _calculate_gateway_fees(db: Session, order: Order) -> Decimal:
    """Calculate payment gateway fees (default 2% of order value; overridable via expense_rules)."""
    order_value = Decimal(str(order.total_amount or 0))
    # Rule-based override (per user)
    try:
        if getattr(order, "user_id", None) and order.created_at:
            rule = _get_applicable_expense_rule(
                db,
                user_id=str(order.user_id),
                rule_type="GATEWAY_FEE",
                on_date=order.created_at.date(),
            )
            if rule:
                return _rule_to_amount(rule, order_value)
    except Exception:
        pass
    return (order_value * Decimal("2") / Decimal("100")).quantize(Decimal("0.01"))


def _calculate_cod_fees(db: Session, order: Order) -> Decimal:
    """Calculate COD fees if order is COD (default 3% of order value; overridable via expense_rules)."""
    if hasattr(order, 'payment_mode') and order.payment_mode and order.payment_mode.value.upper() == 'COD':
        order_value = Decimal(str(order.total_amount or 0))
        try:
            if getattr(order, "user_id", None) and order.created_at:
                rule = _get_applicable_expense_rule(
                    db,
                    user_id=str(order.user_id),
                    rule_type="COD_FEE",
                    on_date=order.created_at.date(),
                )
                if rule:
                    return _rule_to_amount(rule, order_value)
        except Exception:
            pass
        return (order_value * Decimal("3") / Decimal("100")).quantize(Decimal("0.01"))
    return Decimal("0")


def _calculate_packaging_fee(db: Session, order: Order) -> Decimal:
    """Calculate packaging fee via PACKAGING_FEE rule (optional)."""
    order_value = Decimal(str(order.total_amount or 0))
    try:
        if getattr(order, "user_id", None) and order.created_at:
            rule = _get_applicable_expense_rule(
                db,
                user_id=str(order.user_id),
                rule_type="PACKAGING_FEE",
                on_date=order.created_at.date(),
            )
            if rule:
                return _rule_to_amount(rule, order_value)
    except Exception:
        pass
    return Decimal("0")

def _calculate_ad_spend(db: Session, order: Order) -> Decimal:
    """Calculate blended ad spend for order date"""
    from app.models import AdSpendDaily
    
    if not order.created_at:
        return Decimal("0")
    
    order_date = order.created_at.date()
    ad_spend = db.query(AdSpendDaily).filter(AdSpendDaily.date == order_date).first()
    
    if ad_spend:
        # Blend across orders for that day (simplified - could be more sophisticated)
        total_orders_that_day = db.query(Order).filter(
            func.date(Order.created_at) == order_date
        ).count()
        if total_orders_that_day > 0:
            return Decimal(str(ad_spend.spend or 0)) / Decimal(str(total_orders_that_day))
    
    return Decimal("0")


def _calculate_rto_loss(db: Session, order: Order) -> Decimal:
    """Calculate RTO loss if order is RTO"""
    if hasattr(order, 'status') and order.status and order.status.value.upper() in ('RTO', 'RETURNED'):
        # Loss = product cost + forward shipping
        product_cost = _calculate_product_costs(db, order)
        shipment = db.query(Shipment).filter(Shipment.order_id == order.id).first()
        forward_shipping = Decimal(str(shipment.forward_cost or 0)) if shipment else Decimal("0")
        return product_cost + forward_shipping
    
    return Decimal("0")


def _create_order_settlements(db: Session, order: Order, finance_id: str):
    """Create expected settlement records"""
    # Clear existing settlements
    db.query(OrderSettlement).filter(OrderSettlement.order_finance_id == finance_id).delete()
    
    settlements = []
    order_date = order.created_at.date() if order.created_at else date.today()
    
    # Payment gateway settlement (T+7 for prepaid, T+15 for COD)
    if hasattr(order, 'payment_mode') and order.payment_mode:
        if order.payment_mode.value.upper() == 'PREPAID':
            settlement_days = 7
        else:
            settlement_days = 15
        
        settlements.append(OrderSettlement(
            order_id=order.id,
            order_finance_id=finance_id,
            partner="Payment Gateway",
            expected_date=order_date + datetime.timedelta(days=settlement_days),
            amount=Decimal(str(order.total_amount or 0)),
            status=SettlementStatus.PENDING,
            description=f"Expected settlement in {settlement_days} days"
        ))
    
    # Marketplace settlement (T+30)
    settlements.append(OrderSettlement(
        order_id=order.id,
        order_finance_id=finance_id,
        partner="Marketplace",
        expected_date=order_date + datetime.timedelta(days=30),
        amount=Decimal(str(order.total_amount or 0)),
        status=SettlementStatus.PENDING,
        description="Expected marketplace settlement"
    ))
    
    for settlement in settlements:
        db.add(settlement)
    
    db.flush()


def _update_customer_risk(db: Session, order: Order, fulfilment_status: FulfilmentStatus, net_profit: Decimal):
    """Update customer risk profile"""
    customer_id = order.customer_id or f"guest_{order.billing_email or 'unknown'}"
    
    risk = db.query(CustomerRisk).filter(CustomerRisk.customer_id == customer_id).first()
    if not risk:
        risk = CustomerRisk(customer_id=customer_id)
        db.add(risk)
        db.flush()
    
    # Update order counts
    risk.total_orders += 1
    risk.last_order_date = order.created_at.date() if order.created_at else date.today()
    
    # Update RTO count and loss
    if fulfilment_status == FulfilmentStatus.RTO:
        risk.rto_count += 1
        if net_profit < 0:  # Loss scenario
            risk.loss_amount += abs(net_profit)
    
    # Calculate risk score and tag
    rto_ratio = risk.rto_count / risk.total_orders if risk.total_orders > 0 else 0
    
    if rto_ratio > 0.4 or risk.loss_amount > Decimal("1000"):
        risk.risk_tag = RiskTag.HIGH
        risk.risk_score = Decimal("80.0")
    elif rto_ratio > 0.2 or risk.loss_amount > Decimal("500"):
        risk.risk_tag = RiskTag.MEDIUM
        risk.risk_score = Decimal("50.0")
    else:
        risk.risk_tag = RiskTag.SAFE
        risk.risk_score = Decimal("20.0")
    
    risk.last_updated_at = datetime.now()


def get_finance_overview(db: Session, user_id: Optional[str] = None) -> Dict:
    """Get finance overview statistics. Returns keys expected by frontend: revenue, netProfit, loss, rtoPercent, cashPending, codPercent."""
    query = db.query(OrderFinance)
    if user_id:
        query = query.join(Order).filter(Order.user_id == user_id)
    finances = query.all()

    total_orders = len(finances)
    
    # Handle empty data case
    if total_orders == 0:
        return {
            "revenue": 0,
            "netProfit": 0,
            "loss": 0,
            "rtoPercent": 0,
            "cashPending": 0,
            "codPercent": 0,
            "totalOrders": 0
        }
    
    total_revenue = sum(f.revenue_realized or 0 for f in finances)
    total_expenses = sum(f.total_expense or 0 for f in finances)
    total_profit = sum(f.net_profit or 0 for f in finances)
    loss = sum(abs(f.net_profit or 0) for f in finances if f.net_profit and f.net_profit < 0)
    profit_orders = len([f for f in finances if f.profit_status == ProfitStatus.PROFIT])
    loss_orders = len([f for f in finances if f.profit_status == ProfitStatus.LOSS])

    # Cash pending: sum of PENDING settlement amounts
    from app.models import OrderSettlement, SettlementStatus
    settlement_query = db.query(OrderSettlement).join(OrderFinance).join(Order)
    if user_id:
        settlement_query = settlement_query.filter(Order.user_id == user_id)
    pending_settlements = settlement_query.filter(OrderSettlement.status == SettlementStatus.PENDING).all()
    cash_pending = sum(float(s.amount) for s in pending_settlements)

    # COD % and RTO % from orders
    cod_count = 0
    rto_count = 0
    for f in finances:
        o = db.query(Order).filter(Order.id == f.order_id).first()
        if o and getattr(o, "payment_mode", None) and o.payment_mode.value.upper() == "COD":
            cod_count += 1
        if f.fulfilment_status == FulfilmentStatus.RTO:
            rto_count += 1
    cod_percent = (cod_count / total_orders * 100) if total_orders else 0
    rto_percent = (rto_count / total_orders * 100) if total_orders else 0

    return {
        "revenue": float(total_revenue),
        "netProfit": float(total_profit),
        "loss": float(loss),
        "rtoPercent": round(rto_percent, 1),
        "cashPending": round(cash_pending, 2),
        "codPercent": round(cod_percent, 1),
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_expenses": float(total_expenses),
        "total_profit": float(total_profit),
        "profit_orders": profit_orders,
        "loss_orders": loss_orders,
        "profit_margin": float(total_profit / total_revenue * 100) if total_revenue > 0 else 0,
    }
