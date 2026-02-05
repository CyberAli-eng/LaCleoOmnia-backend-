"""
Myntra Partner API service for order retrieval.
Myntra PPMP/Omni API docs: https://mmip.myntrainfo.com/documentation/
Partner-specific credentials and endpoints may apply.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Myntra API base (PPMP v4); may vary by partner
MYNTRA_API_BASE = "https://mmip.myntrainfo.com"


async def get_orders(
    *,
    api_key: str,
    seller_id: str,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """
    Fetch orders from Myntra Partner API.
    Myntra exposes different endpoints per partner; this implements a minimal
    attempt. If your partner portal uses a different base URL or path, set
    MYNTRA_API_BASE or pass full URL in credentials.
    """
    if from_date is None:
        from_date = datetime.now(timezone.utc) - timedelta(days=30)
    if to_date is None:
        to_date = datetime.now(timezone.utc)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # Common pattern: list orders by date range; path may be /api/v4/orders or similar
    url = f"{MYNTRA_API_BASE}/api/v4/orders"
    params = {
        "fromDate": from_date.strftime("%Y-%m-%d"),
        "toDate": to_date.strftime("%Y-%m-%d"),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 404 or resp.status_code == 401:
                logger.info(
                    "Myntra API returned %s; partner-specific endpoint or credentials may be required.",
                    resp.status_code,
                )
                return []
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("Myntra get_orders HTTP error: %s %s", e.response.status_code, e.response.text)
        return []
    except Exception as e:
        logger.warning("Myntra get_orders failed: %s", e)
        return []

    orders = data.get("orders") or data.get("data") or data if isinstance(data, list) else []
    return list(orders) if isinstance(orders, list) else []


def normalize_myntra_order_to_common(order: dict[str, Any]) -> dict[str, Any]:
    """Map one Myntra order to common shape (id, total, customer, items)."""
    order_id = str(order.get("orderId") or order.get("order_id") or order.get("id") or "")
    total = float(order.get("orderValue") or order.get("total") or order.get("amount") or 0)
    items = []
    for line in order.get("orderLines") or order.get("lines") or order.get("items") or []:
        items.append({
            "sku": str(line.get("sellerSku") or line.get("sku") or ""),
            "title": str(line.get("productName") or line.get("title") or "Myntra item"),
            "quantity": int(line.get("quantity") or 1),
            "price": float(line.get("sellingPrice") or line.get("price") or 0),
        })
    if not items:
        items = [{"sku": f"MYN-{order_id}", "title": "Myntra order", "quantity": 1, "price": total}]

    return {
        "id": order_id,
        "channel_order_id": order_id,
        "order_total": total,
        "customer_name": order.get("customerName") or order.get("customer_name") or "Myntra Customer",
        "customer_email": order.get("customerEmail") or order.get("customer_email") or "",
        "financial_status": "paid",
        "payment_mode": "PREPAID",
        "items": items,
        "raw": order,
    }
