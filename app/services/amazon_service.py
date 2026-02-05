"""
Amazon SP-API service for order retrieval.
Uses LWA (Login with Amazon) OAuth; no AWS SigV4 required as of 2023.
Docs: https://developer-docs.amazon.com/sp-api/docs/orders-api
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# SP-API base URL (EU region covers India marketplace)
SP_API_BASE = "https://sellingpartnerapi-eu.amazon.com"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# Default marketplace ID for India
DEFAULT_MARKETPLACE_ID = "A21TJRUUN4KGV"


async def get_lwa_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: float = 15.0,
) -> str:
    """Exchange LWA refresh token for access token."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            LWA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"]


async def get_orders(
    *,
    access_token: str,
    seller_id: str,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    created_after: datetime | None = None,
    max_pages: int = 10,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """
    Fetch orders from Amazon SP-API Orders v0.
    Uses GET orders/v0/orders with CreatedAfter and MarketplaceIds.
    """
    if created_after is None:
        created_after = datetime.now(timezone.utc) - timedelta(days=30)
    if created_after.tzinfo is None:
        created_after = created_after.replace(tzinfo=timezone.utc)
    created_after_str = created_after.strftime("%Y-%m-%dT%H:%M:%SZ")

    all_orders: list[dict[str, Any]] = []
    next_token: str | None = None
    page = 0

    async with httpx.AsyncClient(timeout=timeout) as client:
        while page < max_pages:
            params: dict[str, Any] = {
                "CreatedAfter": created_after_str,
                "MarketplaceIds": marketplace_id,
                "MaxResultsPerPage": 100,
            }
            if next_token:
                params["NextToken"] = next_token

            url = f"{SP_API_BASE}/orders/v0/orders"
            headers = {
                "x-amz-access-token": access_token,
                "Content-Type": "application/json",
            }

            try:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.warning("Amazon SP-API getOrders error: %s %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.exception("Amazon get_orders request failed: %s", e)
                raise

            data = resp.json()
            payload = data.get("payload") or {}
            orders = payload.get("Orders") or []
            all_orders.extend(orders)

            next_token = payload.get("NextToken")
            if not next_token or not orders:
                break
            page += 1

    return all_orders


def normalize_amazon_order_to_common(amazon_order: dict[str, Any]) -> dict[str, Any]:
    """
    Map one Amazon SP-API order (v0) to a common shape: id, total, customer, items, payment.
    Order items in SP-API v0 are not in the list response; we build a single line from order total.
    For full itemization we would need getOrderItems per order (extra API calls).
    """
    order_id = amazon_order.get("AmazonOrderId") or ""
    total = float(amazon_order.get("OrderTotal", {}).get("Amount", 0) or 0)
    currency = (amazon_order.get("OrderTotal") or {}).get("CurrencyCode") or "INR"
    purchase_date = amazon_order.get("PurchaseDate") or ""
    status = amazon_order.get("OrderStatus") or ""

    # Shipping address / buyer info (may be PII; SP-API may require RDT for some fields)
    ship = amazon_order.get("ShippingAddress") or {}
    name = (
        ship.get("Name")
        or (ship.get("AddressLine1") and "Customer")
        or "Amazon Customer"
    )
    email = amazon_order.get("BuyerInfo", {}).get("BuyerEmail") or ""

    # Single “virtual” line item when we don’t have itemization
    items = [
        {
            "sku": f"AMZ-{order_id}",
            "title": "Order (imported from Amazon)",
            "quantity": 1,
            "price": total,
        }
    ]

    return {
        "id": order_id,
        "channel_order_id": order_id,
        "order_total": total,
        "currency": currency,
        "customer_name": name,
        "customer_email": email,
        "financial_status": "paid" if status in ("Shipped", "Unshipped", "PartiallyShipped") else "pending",
        "payment_mode": "PREPAID" if (amazon_order.get("PaymentMethod") or "").lower() != "cod" else "COD",
        "purchase_date": purchase_date,
        "items": items,
        "raw": amazon_order,
    }
