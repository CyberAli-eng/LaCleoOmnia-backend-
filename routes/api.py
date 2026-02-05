"""
Central API route registration. All HTTP controllers are mounted here with /api prefix.
URL paths and behavior are unchanged from the previous structure.
"""
import logging
from fastapi import FastAPI

from app.http.controllers import (
    auth,
    channels,
    orders,
    inventory,
    products,
    warehouses,
    shipments,
    sync,
    config,
    webhooks,
    marketplaces,
    analytics,
    labels,
    workers,
    audit,
    users,
    integrations,
    sku_costs,
    profit,
    mock,
)

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI, settings) -> None:
    """Register all API routers. Call from main.py after creating the FastAPI app."""
    if getattr(settings, "MOCK_DATA", False):
        app.include_router(mock.router, prefix="/api", tags=["mock"])
        logger.info("📦 MOCK_DATA=true: mock API enabled for orders, inventory, analytics, integrations, etc.")

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(channels.router, prefix="/api/channels", tags=["channels"])
    app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
    app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])
    app.include_router(products.router, prefix="/api/products", tags=["products"])
    app.include_router(warehouses.router, prefix="/api/warehouses", tags=["warehouses"])
    app.include_router(shipments.router, prefix="/api/shipments", tags=["shipments"])
    app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
    app.include_router(marketplaces.router, prefix="/api/marketplaces", tags=["marketplaces"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(labels.router, prefix="/api/labels", tags=["labels"])
    app.include_router(workers.router, prefix="/api/workers", tags=["workers"])
    app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    app.include_router(integrations.router, prefix="/api/integrations", tags=["integrations"])
    app.include_router(sku_costs.router, prefix="/api/sku-costs", tags=["sku-costs"])
    app.include_router(profit.router, prefix="/api/profit", tags=["profit"])
