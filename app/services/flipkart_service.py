"""
Flipkart Seller API service for order retrieval.
Uses OAuth2 client_credentials. Docs: https://seller.flipkart.com/api-docs/order-api-docs/
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

FLIPKART_OAUTH_URL = "https://api.flipkart.net/oauth-service/oauth/token"
FLIPKART_ORDERS_SEARCH_URL = "https://api.flipkart.net/sellers/v2/orders/search"


async def get_access_token(
    client_id: str,
    client_secret: str,
    timeout: float = 15.0,
) -> str:
    """Get Flipkart OAuth2 access token using client credentials."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            FLIPKART_OAUTH_URL,
            params={"grant_type": "client_credentials", "scope": "Seller_Api"},
            auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"]


async def get_orders(
    *,
    access_token: str,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    max_pages: int = 20,
    page_size: int = 20,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """
    Fetch orders from Flipkart Seller API (POST /orders/search).
    Returns a list of raw order item objects; we normalize to common shape in order_import.
    """
    if from_date is None:
        from_date = datetime.now(timezone.utc) - timedelta(days=30)
    if to_date is None:
        to_date = datetime.now(timezone.utc)
    for d in (from_date, to_date):
        if d.tzinfo is None:
            d.replace(tzinfo=timezone.utc)  # no-op if already tz-aware; else use IST for Flipkart
    from_str = from_date.strftime("%Y-%m-%dT%H:%M:%S")
    to_str = to_date.strftime("%Y-%m-%dT%H:%M:%S")

    all_items: list[dict[str, Any]] = []
    next_page_url: str | None = None
    page = 0

    async with httpx.AsyncClient(timeout=timeout) as client:
        while page < max_pages:
            if next_page_url:
                url = next_page_url
                body = None
            else:
                url = FLIPKART_ORDERS_SEARCH_URL
                body = {
                    "filter": {
                        "orderDate": {"fromDate": from_str, "toDate": to_str},
                    },
                    "pagination": {"pageSize": min(page_size, 20)},
                    "sort": {"field": "orderDate", "order": "desc"},
                }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            try:
                if body is not None:
                    resp = await client.post(url, json=body, headers=headers)
                else:
                    resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.warning("Flipkart orders/search error: %s %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.exception("Flipkart get_orders failed: %s", e)
                raise

            data = resp.json()
            # Response may have orderItems list and nextPageURL
            items = data.get("orderItems") or data.get("orderItemIds") or []
            if isinstance(items, list):
                all_items.extend(items)
            next_page_url = data.get("nextPageURL") or data.get("nextPageUrl")
            if not next_page_url or not items:
                break
            page += 1

    return all_items


def normalize_flipkart_order_item_to_common(item: dict[str, Any]) -> dict[str, Any]:
    """
    Map one Flipkart order item to common shape. Flipkart returns order items (one per line).
    We group by orderId in order_import; here we return a single-order shape per item for simplicity.
    """
    order_id = item.get("orderId") or item.get("orderItemId") or ""
    order_item_id = item.get("orderItemId") or order_id
    sku = item.get("sellerSkuId") or item.get("skuId") or f"FK-{order_item_id}"
    title = item.get("productTitle") or item.get("title") or "Flipkart order item"
    quantity = int(item.get("quantity") or 1)
    price = float(item.get("sellingPrice") or item.get("price") or 0)
    total = float(item.get("orderItemValue") or price * quantity)

    return {
        "id": order_item_id,
        "channel_order_id": order_id,
        "order_total": total,
        "customer_name": "Flipkart Customer",
        "customer_email": "",
        "financial_status": "paid",
        "payment_mode": "PREPAID",
        "items": [{"sku": sku, "title": title, "quantity": quantity, "price": price}],
        "raw": item,
    }
