"""
Logistics analytics endpoints (RTO dashboard).
"""
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Order, OrderFinance, FulfilmentStatus


router = APIRouter()


PINCODE_RE = re.compile(r"(\b\d{6}\b)")


def _extract_pincode(addr: Optional[str]) -> str:
    if not addr:
        return "unknown"
    m = PINCODE_RE.search(addr)
    return m.group(1) if m else "unknown"


@router.get("/rto")
async def get_rto_dashboard(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    RTO metrics and loss by pincode (best-effort extraction from shipping_address).
    """
    end = date.today()
    start = end - timedelta(days=days)

    # Load orders + finance in window
    rows = (
        db.query(Order, OrderFinance)
        .join(OrderFinance, OrderFinance.order_id == Order.id)
        .filter(Order.user_id == current_user.id)
        .filter(Order.created_at.isnot(None))
        .filter(Order.created_at >= start)
        .all()
    )

    by_pin = defaultdict(lambda: {"orders": 0, "rtoCount": 0, "lossAmount": 0.0})
    total_orders = 0
    total_rto = 0
    total_loss = 0.0

    for order, fin in rows:
        pincode = _extract_pincode(getattr(order, "shipping_address", None))
        by_pin[pincode]["orders"] += 1
        total_orders += 1

        is_rto = fin.fulfilment_status == FulfilmentStatus.RTO
        if is_rto:
            by_pin[pincode]["rtoCount"] += 1
            total_rto += 1
            loss = float(-fin.net_profit) if fin.net_profit and fin.net_profit < 0 else float(fin.total_expense or 0)
            by_pin[pincode]["lossAmount"] += loss
            total_loss += loss

    out_rows = []
    for pin, agg in by_pin.items():
        orders = agg["orders"]
        rto_count = agg["rtoCount"]
        rto_rate = (rto_count / orders * 100) if orders else 0.0
        out_rows.append(
            {
                "pincode": pin,
                "orders": orders,
                "rtoCount": rto_count,
                "rtoRate": rto_rate,
                "lossAmount": agg["lossAmount"],
            }
        )

    out_rows.sort(key=lambda r: (r["lossAmount"], r["rtoCount"]), reverse=True)
    top = out_rows[:20]

    overall_rate = (total_rto / total_orders * 100) if total_orders else 0.0
    return {
        "rtoRate": overall_rate,
        "totalLoss": total_loss,
        "totalOrders": total_orders,
        "rtoCount": total_rto,
        "topPincodes": top,
        "rows": out_rows,
    }

