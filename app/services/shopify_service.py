"""
Shopify Admin API service - authenticated requests.
Uses API version 2024-01 (stable). Never expose access_token to frontend.
Supports cursor pagination (Link header) so we fetch all products, not just first 250.
"""
import re
import httpx
import logging
from typing import Any, Optional

# Use 2024-01 (stable). 2026-01 can be unstable and cause inventory issues.
SHOPIFY_API_VERSION = "2024-01"
logger = logging.getLogger(__name__)


def _parse_link_next(link_header: Optional[str]) -> Optional[str]:
    """Parse Link header; return URL for rel=next if present. Shopify uses cursor pagination."""
    if not link_header:
        return None
    # Format: <url>; rel=next, <url>; rel=previous
    for part in link_header.split(","):
        part = part.strip()
        if "; rel=next" in part.lower():
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1).strip()
    return None


def _log_shopify_response(method: str, url: str, status: int, body_preview: str = "") -> None:
    """Log every Shopify API call for debugging. No sensitive data."""
    if status >= 400:
        logger.warning("Shopify API %s %s -> %s %s", method, url, status, body_preview[:200] if body_preview else "")
    else:
        logger.info("Shopify API %s %s -> %s", method, url, status)


def _base_url(shop_domain: str) -> str:
    shop = shop_domain.lower().strip()
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com" if "." not in shop else shop
    return f"https://{shop}/admin/api/{SHOPIFY_API_VERSION}"


def _headers(access_token: str) -> dict:
    return {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }


def _shop_base_url(shop_domain: str) -> str:
    """Base URL for shop (admin/oauth), not API versioned path."""
    shop = shop_domain.lower().strip()
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com" if "." not in shop else shop
    return f"https://{shop}"


async def get_access_scopes(shop_domain: str, access_token: str) -> list[str]:
    """
    Fetch granted scopes for the current token from Shopify.
    GET /admin/oauth/access_scopes.json
    Returns list of scope handles (e.g. read_locations). Empty list on error.
    """
    url = f"{_shop_base_url(shop_domain)}/admin/oauth/access_scopes.json"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=_headers(access_token), timeout=10.0)
            response.raise_for_status()
        data = response.json()
        scopes = data.get("access_scopes") or []
        return [str(s.get("handle", "")).strip() for s in scopes if s and s.get("handle")]
    except Exception as e:
        logger.warning("Could not fetch Shopify access_scopes: %s", e)
        return []


async def get_orders(shop_domain: str, access_token: str, limit: int = 250) -> list[dict]:
    """
    Fetch orders from Shopify Admin API.
    GET /admin/api/2024-01/orders.json
    Returns normalized list of orders (id, customer, total, status, created_at).
    """
    url = f"{_base_url(shop_domain)}/orders.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params={"status": "any", "limit": limit},
            headers=_headers(access_token),
            timeout=30.0,
        )
        response.raise_for_status()
    data = response.json()
    raw_orders = data.get("orders", [])
    return [
        {
            "id": str(o.get("id")),
            "order_id": str(o.get("id")),
            "customer": (o.get("customer") or {}).get("email") or o.get("email") or "—",
            "customer_name": _order_customer_name(o),
            "total": float(o.get("total_price", 0) or 0),
            "status": (o.get("fulfillment_status") or o.get("financial_status") or "unknown"),
            "created_at": o.get("created_at") or "",
        }
        for o in raw_orders
    ]


def _order_customer_name(o: dict) -> str:
    """First name + last name or email for display."""
    c = o.get("customer") or {}
    first = (c.get("first_name") or "").strip()
    last = (c.get("last_name") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    return (o.get("email") or "").strip() or "—"


async def get_orders_raw(shop_domain: str, access_token: str, limit: int = 250) -> list[dict]:
    """Fetch raw orders from Shopify for sync (full payload including line_items)."""
    url = f"{_base_url(shop_domain)}/orders.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params={"status": "any", "limit": limit},
            headers=_headers(access_token),
            timeout=30.0,
        )
        response.raise_for_status()
    data = response.json()
    return data.get("orders", [])


async def get_products(shop_domain: str, access_token: str, limit: int = 250) -> list[dict]:
    """
    Fetch one page of products from Shopify Admin API.
    GET /admin/api/2024-01/products.json
    """
    url = f"{_base_url(shop_domain)}/products.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            params={"limit": limit},
            headers=_headers(access_token),
            timeout=30.0,
        )
        response.raise_for_status()
    data = response.json()
    return data.get("products", [])


async def get_products_all_pages(shop_domain: str, access_token: str, page_limit: int = 250) -> list[dict]:
    """
    Fetch all products using cursor pagination (Link header).
    Stops when response has no rel=next or fewer than page_limit items.
    """
    base = _base_url(shop_domain)
    h = _headers(access_token)
    url = f"{base}/products.json"
    params: dict = {"limit": page_limit}
    all_products: list[dict] = []
    page = 0
    async with httpx.AsyncClient() as client:
        while True:
            page += 1
            response = await client.get(url, params=params, headers=h, timeout=30.0)
            body = response.text[:300] if response.text else ""
            _log_shopify_response("GET", url, response.status_code, body)
            response.raise_for_status()
            data = response.json()
            products = data.get("products") or []
            all_products.extend(products)
            logger.info("Shopify products page %s: got %s (total so far: %s)", page, len(products), len(all_products))
            if len(products) < page_limit:
                break
            next_url = _parse_link_next(response.headers.get("link"))
            if not next_url:
                break
            url = next_url
            params = {}  # page_info URL already has params; do not add extra
    logger.info("Shopify products: got %s product(s) across %s page(s)", len(all_products), page)
    return all_products


async def get_locations(shop_domain: str, access_token: str) -> list[dict]:
    """
    Step 3 of inventory pipeline. Required for inventory_levels (API needs location_ids).
    Returns list of location dicts; empty list on error.
    """
    base = _base_url(shop_domain)
    url = f"{base}/locations.json"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"limit": 50},
                headers=_headers(access_token),
                timeout=15.0,
            )
            body = response.text[:300] if response.text else ""
            _log_shopify_response("GET", url, response.status_code, body)
            response.raise_for_status()
        data = response.json()
        locs = data.get("locations") or []
        logger.info("Shopify locations: got %s location(s)", len(locs))
        return locs
    except Exception as e:
        logger.warning("Shopify locations failed (read_locations scope): %s", e)
        return []


def _variants_from_products(products: list[dict]) -> list[dict]:
    """
    Step 2: Extract variant.id, variant.sku, variant.inventory_item_id, product title.
    Returns list of { variant_id, sku, inventory_item_id, product_title }.
    """
    out: list[dict] = []
    for p in products or []:
        if not isinstance(p, dict):
            continue
        title = (p.get("title") or "").strip() or "—"
        for v in p.get("variants") or []:
            if not isinstance(v, dict):
                continue
            inv_item_id = v.get("inventory_item_id")
            if inv_item_id is None:
                continue
            out.append({
                "variant_id": v.get("id"),
                "sku": (v.get("sku") or "").strip() or "—",
                "inventory_item_id": inv_item_id,
                "product_title": title,
            })
    return out


async def get_inventory(shop_domain: str, access_token: str) -> list[dict]:
    """
    Full inventory pipeline (no silent fails):
    1) GET products.json
    2) Extract variant.id, variant.sku, variant.inventory_item_id, product title
    3) GET locations.json
    4) GET inventory_levels.json?inventory_item_ids=...&location_ids=...
    5) Merge into normalized: sku, product_name, variant_id, inventory_item_id, location_id, available
    Defensive: never raises. Returns [] on error. Logs every step.
    """
    base = _base_url(shop_domain)
    h = _headers(access_token)

    # Step 1: Get all products (paginated; not just first 250)
    products: list[dict] = []
    try:
        products = await get_products_all_pages(shop_domain, access_token, page_limit=250)
    except (httpx.HTTPStatusError, Exception) as e:
        logger.warning("Shopify products failed (read_products scope): %s", e)
        return []

    # Step 2: Extract variants with inventory_item_id
    variants = _variants_from_products(products)
    if not variants:
        logger.warning("Shopify inventory: no variants with inventory_item_id found")
        return []

    inventory_item_ids = [v["inventory_item_id"] for v in variants if v.get("inventory_item_id") is not None]
    inv_by_id = {v["inventory_item_id"]: v for v in variants}

    # Step 3: Get locations
    locs = await get_locations(shop_domain, access_token)
    location_ids = [loc["id"] for loc in locs if isinstance(loc, dict) and loc.get("id") is not None]
    if not location_ids:
        logger.warning("Shopify inventory: no locations (read_locations required); levels may be empty")

    # Step 4: Get inventory levels (need both params for full data)
    levels: list[dict] = []
    try:
        url = f"{base}/inventory_levels.json"
        params: dict = {"limit": 250}
        if inventory_item_ids:
            params["inventory_item_ids"] = ",".join(str(x) for x in inventory_item_ids[:250])
        if location_ids:
            params["location_ids"] = ",".join(str(x) for x in location_ids[:50])
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=h, timeout=30.0)
            body = response.text[:300] if response.text else ""
            _log_shopify_response("GET", url, response.status_code, body)
            response.raise_for_status()
        data = response.json()
        levels = data.get("inventory_levels") or []
        logger.info("Shopify inventory_levels: got %s level(s)", len(levels))
    except (httpx.HTTPStatusError, Exception) as e:
        logger.warning("Shopify inventory_levels failed (read_inventory, read_locations): %s", e)
        levels = []

    # Step 5: Merge
    result: list[dict] = []
    for lev in levels or []:
        if not isinstance(lev, dict):
            continue
        iid = lev.get("inventory_item_id")
        v = inv_by_id.get(iid) if iid is not None else None
        sku = (v.get("sku") or "—") if v else "—"
        product_name = (v.get("product_title") or sku) if v else "—"
        result.append({
            "sku": sku,
            "product_name": product_name,
            "variant_id": v.get("variant_id") if v else None,
            "inventory_item_id": iid,
            "location_id": lev.get("location_id"),
            "location": str(lev.get("location_id") or ""),
            "available": int(lev.get("available", 0) or 0),
        })
    # Include variants that have no level (0 available)
    seen = {(r.get("inventory_item_id"), r.get("location_id")): True for r in result}
    for v in variants:
        if not location_ids:
            if not any(r.get("inventory_item_id") == v.get("inventory_item_id") for r in result):
                result.append({
                    "sku": v.get("sku") or "—",
                    "product_name": v.get("product_title") or "—",
                    "variant_id": v.get("variant_id"),
                    "inventory_item_id": v.get("inventory_item_id"),
                    "location_id": None,
                    "location": "",
                    "available": 0,
                })
        else:
            for loc_id in location_ids:
                if (v.get("inventory_item_id"), loc_id) not in seen:
                    result.append({
                        "sku": v.get("sku") or "—",
                        "product_name": v.get("product_title") or "—",
                        "variant_id": v.get("variant_id"),
                        "inventory_item_id": v.get("inventory_item_id"),
                        "location_id": loc_id,
                        "location": str(loc_id),
                        "available": 0,
                    })
    return result
