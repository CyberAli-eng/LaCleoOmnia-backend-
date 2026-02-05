"""
Profit engine: compute net_profit per order from revenue, SKU costs, shipment (forward/reverse), courier status, and marketing CAC.
Rules: Delivered = revenue - all costs; RTO = loss (product+packaging+forward+reverse+marketing); Lost = product+packaging+forward; Cancelled = marketing+payment.
Marketing cost = blended CAC from ad_spend_daily (daily_spend / daily_orders for order date).
"""
import logging
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    Order,
    OrderItem,
    SkuCost,
    OrderProfit,
    Shipment,
    ShipmentStatus,
    OrderStatus,
    AdSpendDaily,
)

logger = logging.getLogger(__name__)


def _get_daily_cac(db: Session, order_date: date) -> Decimal:
    """Blended CAC for a calendar day: daily_spend / daily_orders. Returns 0 if no orders or no spend."""
    daily_spend = db.query(func.coalesce(func.sum(AdSpendDaily.spend), 0)).filter(
        AdSpendDaily.date == order_date
    ).scalar()
    daily_spend = Decimal(str(daily_spend or 0))
    daily_orders = db.query(func.count(Order.id)).filter(
        func.date(Order.created_at) == order_date
    ).scalar() or 0
    if daily_orders <= 0:
        return Decimal("0")
    return (daily_spend / daily_orders).quantize(Decimal("0.01"))


def compute_profit_for_order(db: Session, order_id: str) -> OrderProfit | None:
    """
    Compute profit for an order and upsert order_profit.
    Uses shipment status (DELIVERED, RTO_DONE, RTO_INITIATED, LOST) and order status (CANCELLED) for rules.
    Returns OrderProfit row or None if order not found.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return None

    revenue = Decimal(str(order.order_total or 0))
    product_cost = Decimal("0")
    packaging_cost = Decimal("0")
    shipping_forward = Decimal("0")
    shipping_reverse = Decimal("0")
    marketing_cost = Decimal("0")
    payment_fee = Decimal("0")
    status = "computed"
    missing_skus: list[str] = []
    courier_status: str | None = None
    final_status: str = "PENDING"
    rto_loss = Decimal("0")
    lost_loss = Decimal("0")

    # Product + packaging from SKU costs
    for item in order.items or []:
        sku = (item.sku or "").strip()
        qty = int(item.qty or 0)
        if not sku or qty <= 0:
            continue
        cost_row = db.query(SkuCost).filter(SkuCost.sku == sku).first()
        if cost_row:
            unit_product = Decimal(str(cost_row.product_cost or 0))
            unit_packaging = Decimal(str(cost_row.packaging_cost or 0))
            product_cost += unit_product * qty
            packaging_cost += unit_packaging * qty
        else:
            missing_skus.append(sku)

    if missing_skus:
        status = "partial" if product_cost > 0 else "missing_costs"
        logger.debug("Order %s profit: missing sku_costs for %s", order_id, missing_skus[:5])

    # Shipment: forward/reverse cost and courier status
    shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()
    if shipment:
        shipping_forward = Decimal(str(shipment.forward_cost or 0))
        shipping_reverse = Decimal(str(shipment.reverse_cost or 0))
        courier_status = shipment.status.value if hasattr(shipment.status, "value") else str(shipment.status)

    # Marketing: blended CAC from ad_spend_daily for order date
    order_date = order.created_at.date() if order.created_at else None
    if order_date:
        marketing_cost = _get_daily_cac(db, order_date)

    # Apply rules by final status
    if order.status == OrderStatus.CANCELLED and (not shipment or shipment.status == ShipmentStatus.CREATED):
        # Cancelled (pre-ship): loss = marketing + payment
        final_status = "CANCELLED"
        net_profit = -(marketing_cost + payment_fee)
        revenue = Decimal("0")
    elif shipment and shipment.status == ShipmentStatus.DELIVERED:
        # Delivered: profit = revenue - all costs
        final_status = "DELIVERED"
        net_profit = revenue - product_cost - packaging_cost - shipping_forward - marketing_cost - payment_fee
    elif shipment and shipment.status in (ShipmentStatus.RTO_DONE, ShipmentStatus.RTO_INITIATED):
        # RTO: loss = product + packaging + forward + reverse + marketing; revenue = 0
        final_status = "RTO_DONE" if shipment.status == ShipmentStatus.RTO_DONE else "RTO_INITIATED"
        rto_loss = product_cost + packaging_cost + shipping_forward + shipping_reverse + marketing_cost
        net_profit = -rto_loss
        revenue = Decimal("0")
    elif shipment and shipment.status == ShipmentStatus.LOST:
        # Lost: loss = product + packaging + forward
        final_status = "LOST"
        lost_loss = product_cost + packaging_cost + shipping_forward
        net_profit = -lost_loss
        revenue = Decimal("0")
    else:
        # Pending / In Transit / CREATED / SHIPPED: standard formula (revenue - costs)
        if shipment and shipment.status == ShipmentStatus.IN_TRANSIT:
            final_status = "IN_TRANSIT"
        elif shipment and shipment.status == ShipmentStatus.SHIPPED:
            final_status = "SHIPPED"
        net_profit = revenue - product_cost - packaging_cost - shipping_forward - marketing_cost - payment_fee

    # Keep shipping_cost in sync with forward for backward compat
    shipping_cost = shipping_forward

    existing = db.query(OrderProfit).filter(OrderProfit.order_id == order_id).first()
    if existing:
        existing.revenue = revenue
        existing.product_cost = product_cost
        existing.packaging_cost = packaging_cost
        existing.shipping_cost = shipping_cost
        existing.shipping_forward = shipping_forward
        existing.shipping_reverse = shipping_reverse
        existing.marketing_cost = marketing_cost
        existing.payment_fee = payment_fee
        existing.net_profit = net_profit
        existing.rto_loss = rto_loss
        existing.lost_loss = lost_loss
        existing.courier_status = courier_status
        existing.final_status = final_status
        existing.status = status
        db.flush()
        return existing
    else:
        row = OrderProfit(
            order_id=order_id,
            revenue=revenue,
            product_cost=product_cost,
            packaging_cost=packaging_cost,
            shipping_cost=shipping_cost,
            shipping_forward=shipping_forward,
            shipping_reverse=shipping_reverse,
            marketing_cost=marketing_cost,
            payment_fee=payment_fee,
            net_profit=net_profit,
            rto_loss=rto_loss,
            lost_loss=lost_loss,
            courier_status=courier_status,
            final_status=final_status,
            status=status,
        )
        db.add(row)
        db.flush()
        return row
