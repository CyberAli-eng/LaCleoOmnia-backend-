"""
Order Finance Engine - Comprehensive financial ledger for orders
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.models import (
    Order, OrderFinance, OrderExpense, OrderSettlement, CustomerRisk,
    OrderItem, Shipment, SkuCost,
    PaymentType, FulfilmentStatus, ProfitStatus, ExpenseType, ExpenseSource, SettlementStatus, RiskTag
)
from app.services.credentials import decrypt_token
import json

logger = logging.getLogger(__name__)


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
    fulfilment_status = _determine_fulfilment_status(order)
    
    # Calculate revenue based on PRD rules
    revenue_realized = _calculate_revenue(order, payment_type, fulfilment_status)
    
    # Get or create OrderFinance record
    finance = db.query(OrderFinance).filter(OrderFinance.order_id == order_id).first()
    if not finance:
        finance = OrderFinance(
            order_id=order_id,
            payment_type=payment_type,
            fulfilment_status=fulfilment_status
        )
        db.add(finance)
        db.flush()
    
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
    finance.profit_status = ProfitStatus.PROFIT if net_profit > 0 else ProfitStatus.LOSS
    
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


def _determine_fulfilment_status(order: Order) -> FulfilmentStatus:
    """Determine fulfilment status from order data"""
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
    expenses = []
    effective_date = order.created_at.date() if order.created_at else date.today()
    
    # Clear existing expenses for this finance record
    db.query(OrderExpense).filter(OrderExpense.order_finance_id == finance_id).delete()
    
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
    gateway_fee = _calculate_gateway_fees(order)
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
    cod_fee = _calculate_cod_fees(order)
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
    return expenses


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


def _calculate_gateway_fees(order: Order) -> Decimal:
    """Calculate payment gateway fees (typically 2% of order value)"""
    order_value = Decimal(str(order.total_amount or 0))
    return order_value * Decimal("0.02")  # 2% gateway fee


def _calculate_cod_fees(order: Order) -> Decimal:
    """Calculate COD fees if order is COD"""
    if hasattr(order, 'payment_mode') and order.payment_mode and order.payment_mode.value.upper() == 'COD':
        order_value = Decimal(str(order.total_amount or 0))
        return order_value * Decimal("0.03")  # 3% COD fee
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
    """Get finance overview statistics"""
    query = db.query(OrderFinance)
    
    if user_id:
        query = query.join(Order).filter(Order.user_id == user_id)
    
    finances = query.all()
    
    total_orders = len(finances)
    total_revenue = sum(f.revenue_realized for f in finances)
    total_expenses = sum(f.total_expense for f in finances)
    total_profit = sum(f.net_profit for f in finances)
    
    profit_orders = len([f for f in finances if f.profit_status == ProfitStatus.PROFIT])
    loss_orders = len([f for f in finances if f.profit_status == ProfitStatus.LOSS])
    
    return {
        "total_orders": total_orders,
        "total_revenue": float(total_revenue),
        "total_expenses": float(total_expenses),
        "total_profit": float(total_profit),
        "profit_orders": profit_orders,
        "loss_orders": loss_orders,
        "profit_margin": float(total_profit / total_revenue * 100) if total_revenue > 0 else 0
    }
