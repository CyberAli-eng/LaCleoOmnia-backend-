"""
Mock API router. When MOCK_DATA=true, these routes are registered first under /api
and return fixture data so the app works without DB or external services.
"""
from fastapi import APIRouter, Request
from app.mock_data import (
    MOCK_LOGIN_RESPONSE,
    MOCK_ME_RESPONSE,
    MOCK_ORDERS_LIST,
    MOCK_ORDER_DETAIL,
    MOCK_INVENTORY_LIST,
    MOCK_SHOPIFY_INVENTORY,
    MOCK_ANALYTICS_SUMMARY,
    MOCK_PROFIT_SUMMARY,
    MOCK_CONFIG_STATUS,
    MOCK_SHOPIFY_STATUS,
    MOCK_SYNC_JOBS,
    MOCK_INTEGRATIONS_CATALOG,
    MOCK_WEBHOOKS_LIST,
    MOCK_WEBHOOK_SUBSCRIPTIONS,
    MOCK_WORKERS_LIST,
)

router = APIRouter()


# ----- Auth -----
@router.post("/auth/login")
async def mock_login(request: Request):
    """Mock login: accept any body, return fake token and user."""
    return MOCK_LOGIN_RESPONSE


@router.get("/auth/me")
async def mock_me():
    return MOCK_ME_RESPONSE


@router.post("/auth/logout")
async def mock_logout():
    return {"message": "Logged out"}


# ----- Orders -----
@router.get("/orders")
async def mock_list_orders():
    return MOCK_ORDERS_LIST


@router.get("/orders/{order_id}")
async def mock_get_order(order_id: str):
    return MOCK_ORDER_DETAIL


# ----- Inventory -----
@router.get("/inventory")
async def mock_list_inventory():
    return MOCK_INVENTORY_LIST


# ----- Analytics -----
@router.get("/analytics/summary")
async def mock_analytics_summary():
    return MOCK_ANALYTICS_SUMMARY


@router.get("/analytics/profit-summary")
async def mock_profit_summary():
    return MOCK_PROFIT_SUMMARY


# ----- Config -----
@router.get("/config/status")
async def mock_config_status():
    return MOCK_CONFIG_STATUS


# ----- Integrations -----
@router.get("/integrations/catalog")
async def mock_integrations_catalog():
    return MOCK_INTEGRATIONS_CATALOG


@router.get("/integrations/shopify/status")
async def mock_shopify_status():
    return MOCK_SHOPIFY_STATUS


@router.get("/integrations/shopify/orders")
async def mock_shopify_orders():
    return MOCK_ORDERS_LIST


@router.get("/integrations/shopify/inventory")
async def mock_shopify_inventory():
    return MOCK_SHOPIFY_INVENTORY


# ----- Sync / Workers -----
@router.get("/sync/jobs")
async def mock_sync_jobs():
    return MOCK_SYNC_JOBS


@router.get("/workers")
async def mock_workers():
    return MOCK_WORKERS_LIST


# ----- Webhooks -----
@router.get("/webhooks")
async def mock_webhooks():
    return MOCK_WEBHOOKS_LIST


@router.get("/webhooks/subscriptions")
async def mock_webhooks_subscriptions():
    return MOCK_WEBHOOK_SUBSCRIPTIONS


# ----- Warehouses (minimal for inventory page) -----
@router.get("/warehouses")
async def mock_warehouses():
    return {
        "warehouses": [
            {"id": "wh-1", "name": "Main Warehouse", "city": "Bangalore", "state": "Karnataka"},
        ]
    }


# ----- Provider status (for integrations page) -----
@router.get("/integrations/providers/{provider_id}/status")
async def mock_provider_status(provider_id: str):
    return {"connected": False, "source": None, "configured": False}
