"""
Analytics routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Order, User, ChannelAccount, OrderProfit, OrderStatus
from app.auth import get_current_user
from datetime import datetime, timedelta, timezone, date

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/overview")
async def get_dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Unicommerce-style dashboard overview: Section 1 (Revenue & Orders today vs yesterday),
    Section 2 (Order Alerts, Product Alerts, Channel Alerts). Used by the main dashboard UI.
    """
    try:
        from app.models import OrderItem, Inventory

        channel_accounts = db.query(ChannelAccount).filter(
            ChannelAccount.user_id == current_user.id
        ).all()
        channel_account_ids = [ca.id for ca in channel_accounts]
        connected_count = sum(
            1 for c in channel_accounts
            if getattr(c, "status", None) and str(getattr(c.status, "value", c.status)) == "CONNECTED"
        )

        if not channel_account_ids:
            return {
                "todayRevenue": 0,
                "yesterdayRevenue": 0,
                "todayOrders": 0,
                "yesterdayOrders": 0,
                "todayItems": 0,
                "yesterdayItems": 0,
                "orderAlerts": {"pendingOrders": 0, "pendingShipment": 0},
                "productAlerts": {"lowStockCount": 0},
                "channelAlerts": {"connectedCount": 0},
                "recentOrders": [],
            }

        today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)
        yesterday_start = today_start - timedelta(days=1)

        # Today/yesterday revenue and order count (by created_at)
        orders_today = db.query(Order).filter(
            Order.channel_account_id.in_(channel_account_ids),
            Order.created_at >= today_start,
            Order.created_at < today_end,
        ).all()
        orders_yesterday = db.query(Order).filter(
            Order.channel_account_id.in_(channel_account_ids),
            Order.created_at >= yesterday_start,
            Order.created_at < today_start,
        ).all()
        today_revenue = sum(float(o.order_total or 0) for o in orders_today)
        yesterday_revenue = sum(float(o.order_total or 0) for o in orders_yesterday)
        today_orders = len(orders_today)
        yesterday_orders = len(orders_yesterday)
        today_ids = [o.id for o in orders_today]
        yesterday_ids = [o.id for o in orders_yesterday]
        today_items = db.query(func.coalesce(func.sum(OrderItem.qty), 0)).filter(
            OrderItem.order_id.in_(today_ids)
        ).scalar() if today_ids else 0
        yesterday_items = db.query(func.coalesce(func.sum(OrderItem.qty), 0)).filter(
            OrderItem.order_id.in_(yesterday_ids)
        ).scalar() if yesterday_ids else 0
        today_items = int(today_items or 0)
        yesterday_items = int(yesterday_items or 0)

        # Order alerts: pending (NEW/HOLD/CONFIRMED), pending shipment (CONFIRMED/PACKED)
        pending_orders = db.query(func.count(Order.id)).filter(
            Order.channel_account_id.in_(channel_account_ids),
            Order.status.in_([OrderStatus.NEW, OrderStatus.HOLD, OrderStatus.CONFIRMED]),
        ).scalar() or 0
        pending_shipment = db.query(func.count(Order.id)).filter(
            Order.channel_account_id.in_(channel_account_ids),
            Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PACKED]),
        ).scalar() or 0

        # Low stock: variants from user's orders where inventory available < 10
        variant_ids = [
            r[0] for r in db.query(OrderItem.variant_id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.channel_account_id.in_(channel_account_ids))
            .filter(OrderItem.variant_id.isnot(None))
            .distinct()
            .all()
        ]
        low_stock_count = 0
        if variant_ids:
            invs = db.query(Inventory).filter(Inventory.variant_id.in_(variant_ids)).all()
            for inv in invs:
                avail = (inv.total_qty or 0) - (inv.reserved_qty or 0)
                if avail < 10:
                    low_stock_count += 1

        # Recent orders
        recent = (
            db.query(Order)
            .filter(Order.channel_account_id.in_(channel_account_ids))
            .order_by(Order.created_at.desc())
            .limit(10)
            .all()
        )
        recent_orders = [
            {
                "id": o.id,
                "externalId": o.channel_order_id,
                "source": o.channel.name.value if o.channel else "Unknown",
                "status": getattr(o.status, "value", str(o.status)),
                "total": float(o.order_total or 0),
                "createdAt": o.created_at.isoformat() if o.created_at else None,
            }
            for o in recent
        ]

        return {
            "todayRevenue": round(today_revenue, 2),
            "yesterdayRevenue": round(yesterday_revenue, 2),
            "todayOrders": today_orders,
            "yesterdayOrders": yesterday_orders,
            "todayItems": today_items,
            "yesterdayItems": yesterday_items,
            "orderAlerts": {"pendingOrders": int(pending_orders), "pendingShipment": int(pending_shipment)},
            "productAlerts": {"lowStockCount": low_stock_count},
            "channelAlerts": {"connectedCount": connected_count},
            "recentOrders": recent_orders,
        }
    except Exception as e:
        logger.error("Error in dashboard overview: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get analytics summary"""
    try:
        # Get channel accounts for the current user
        channel_accounts = db.query(ChannelAccount).filter(
            ChannelAccount.user_id == current_user.id
        ).all()
        
        channel_account_ids = [ca.id for ca in channel_accounts]
        
        # Get orders for the current user (through channel accounts)
        if channel_account_ids:
            orders = db.query(Order).filter(
                Order.channel_account_id.in_(channel_account_ids)
            ).all()
        else:
            orders = []
        
        # Calculate summary from DB only (single source of truth)
        total_orders = len(orders)
        total_revenue = sum(float(o.order_total or 0) for o in orders)
        recent_orders = [
            {
                "id": order.id,
                "externalId": order.channel_order_id,
                "source": order.channel.name.value if order.channel else "Unknown",
                "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                "total": float(order.order_total) if order.order_total else 0.0,
                "createdAt": order.created_at.isoformat() if order.created_at else None,
            }
            for order in sorted(orders, key=lambda x: x.created_at or datetime.min, reverse=True)[:10]
        ]
        
        return {
            "totalOrders": total_orders,
            "totalRevenue": total_revenue,
            "recentOrders": recent_orders,
        }
    except Exception as e:
        logger.error(f"Error in analytics summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching analytics: {str(e)}"
        )


@router.get("/profit-summary")
async def get_profit_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return profit analytics: revenue, net_profit, margin %, loss buckets (orders with net_profit < 0).
    RTO/Loss counts and amounts are placeholders until Delhivery tracking is wired.
    """
    try:
        channel_accounts = db.query(ChannelAccount).filter(
            ChannelAccount.user_id == current_user.id
        ).all()
        channel_account_ids = [ca.id for ca in channel_accounts]
        if not channel_account_ids:
            return {
                "revenue": 0,
                "netProfit": 0,
                "marginPercent": 0,
                "orderCount": 0,
                "lossCount": 0,
                "lossAmount": 0,
                "rtoCount": 0,
                "rtoAmount": 0,
                "lostCount": 0,
                "lostAmount": 0,
                "courierLossPercent": 0,
            }
        # Aggregate from order_profit for user's orders
        q = (
            db.query(
                func.coalesce(func.sum(OrderProfit.revenue), 0).label("revenue"),
                func.coalesce(func.sum(OrderProfit.net_profit), 0).label("net_profit"),
                func.count(OrderProfit.id).label("order_count"),
            )
            .join(Order, Order.id == OrderProfit.order_id)
            .filter(Order.channel_account_id.in_(channel_account_ids))
        )
        row = q.first()
        revenue = float(row.revenue or 0)
        net_profit = float(row.net_profit or 0)
        order_count = int(row.order_count or 0)
        margin_percent = (net_profit / revenue * 100) if revenue else 0
        # Loss bucket: orders where net_profit < 0
        loss_q = (
            db.query(
                func.count(OrderProfit.id).label("cnt"),
                func.coalesce(func.sum(OrderProfit.net_profit), 0).label("amt"),
            )
            .join(Order, Order.id == OrderProfit.order_id)
            .filter(Order.channel_account_id.in_(channel_account_ids))
            .filter(OrderProfit.net_profit < 0)
        )
        loss_row = loss_q.first()
        loss_count = int(loss_row.cnt or 0)
        loss_amount = abs(float(loss_row.amt or 0))
        # RTO / Lost from order_profit (Delhivery tracking)
        rto_q = (
            db.query(
                func.coalesce(func.sum(OrderProfit.rto_loss), 0).label("amt"),
                func.count(OrderProfit.id).label("cnt"),
            )
            .join(Order, Order.id == OrderProfit.order_id)
            .filter(Order.channel_account_id.in_(channel_account_ids))
            .filter(OrderProfit.final_status.in_(["RTO_DONE", "RTO_INITIATED"]))
        )
        rto_row = rto_q.first()
        rto_amount = float(rto_row.amt or 0)
        rto_count = int(rto_row.cnt or 0)
        lost_q = (
            db.query(
                func.coalesce(func.sum(OrderProfit.lost_loss), 0).label("amt"),
                func.count(OrderProfit.id).label("cnt"),
            )
            .join(Order, Order.id == OrderProfit.order_id)
            .filter(Order.channel_account_id.in_(channel_account_ids))
            .filter(OrderProfit.final_status == "LOST")
        )
        lost_row = lost_q.first()
        lost_amount = float(lost_row.amt or 0)
        lost_count = int(lost_row.cnt or 0)
        courier_loss_total = rto_amount + lost_amount
        courier_loss_percent = (courier_loss_total / revenue * 100) if revenue else 0
        return {
            "revenue": round(revenue, 2),
            "netProfit": round(net_profit, 2),
            "marginPercent": round(margin_percent, 2),
            "orderCount": order_count,
            "lossCount": loss_count,
            "lossAmount": round(loss_amount, 2),
            "rtoCount": rto_count,
            "rtoAmount": round(rto_amount, 2),
            "lostCount": lost_count,
            "lostAmount": round(lost_amount, 2),
            "courierLossPercent": round(courier_loss_percent, 2),
        }
    except Exception as e:
        logger.error("Error in profit-summary: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching profit summary: {str(e)}")
