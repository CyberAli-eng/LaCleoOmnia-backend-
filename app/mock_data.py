"""
Mock API responses for development and testing.
Enable with MOCK_DATA=true (or 1/yes). Used by app/routers/mock.py.
"""
from datetime import datetime, timedelta

# Fixed "now" for consistent mock data
_MOCK_NOW = datetime.utcnow()
_MOCK_ORDER_ID = "mock-order-001"
_MOCK_ORDER_ID_2 = "mock-order-002"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
MOCK_LOGIN_RESPONSE = {
    "token": "mock-jwt-token-for-development",
    "user": {
        "id": "mock-user-001",
        "name": "Mock User",
        "email": "mock@lacleoomnia.com",
        "role": "ADMIN",
    },
}

MOCK_ME_RESPONSE = {
    "id": "mock-user-001",
    "name": "Mock User",
    "email": "mock@lacleoomnia.com",
    "role": "ADMIN",
}

# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
MOCK_ORDERS_LIST = {
    "orders": [
        {
            "id": _MOCK_ORDER_ID,
            "channelOrderId": "SHOP-1001",
            "customerName": "Rahul Sharma",
            "customerEmail": "rahul@example.com",
            "shippingAddress": "123 MG Road, Bangalore, Karnataka 560001",
            "billingAddress": "123 MG Road, Bangalore, Karnataka 560001",
            "paymentMode": "PREPAID",
            "orderTotal": 2499.00,
            "status": "CONFIRMED",
            "createdAt": (_MOCK_NOW - timedelta(days=2)).isoformat() + "Z",
            "items": [
                {"id": "oi-1", "sku": "SKU-001", "title": "Classic Tee Blue", "qty": 2, "price": 999.00, "fulfillmentStatus": "MAPPED"},
                {"id": "oi-2", "sku": "SKU-002", "title": "Cotton Socks", "qty": 1, "price": 501.00, "fulfillmentStatus": "MAPPED"},
            ],
        },
        {
            "id": _MOCK_ORDER_ID_2,
            "channelOrderId": "SHOP-1002",
            "customerName": "Priya Patel",
            "customerEmail": "priya@example.com",
            "shippingAddress": "45 Park Street, Mumbai, Maharashtra 400001",
            "billingAddress": "45 Park Street, Mumbai, Maharashtra 400001",
            "paymentMode": "COD",
            "orderTotal": 1899.00,
            "status": "NEW",
            "createdAt": (_MOCK_NOW - timedelta(days=1)).isoformat() + "Z",
            "items": [
                {"id": "oi-3", "sku": "SKU-003", "title": "Summer Dress", "qty": 1, "price": 1899.00, "fulfillmentStatus": "PENDING"},
            ],
        },
    ]
}

MOCK_ORDER_DETAIL = {
    "order": {
        "id": _MOCK_ORDER_ID,
        "channelOrderId": "SHOP-1001",
        "customerName": "Rahul Sharma",
        "customerEmail": "rahul@example.com",
        "shippingAddress": "123 MG Road, Bangalore, Karnataka 560001",
        "billingAddress": "123 MG Road, Bangalore, Karnataka 560001",
        "paymentMode": "PREPAID",
        "orderTotal": 2499.00,
        "status": "CONFIRMED",
        "createdAt": (_MOCK_NOW - timedelta(days=2)).isoformat() + "Z",
        "items": [
            {"id": "oi-1", "sku": "SKU-001", "title": "Classic Tee Blue", "qty": 2, "price": 999.00, "fulfillmentStatus": "MAPPED"},
            {"id": "oi-2", "sku": "SKU-002", "title": "Cotton Socks", "qty": 1, "price": 501.00, "fulfillmentStatus": "MAPPED"},
        ],
        "profit": {
            "revenue": 2499.00,
            "productCost": 800.00,
            "packagingCost": 50.00,
            "shippingCost": 0,
            "shippingForward": 80.00,
            "shippingReverse": 0,
            "marketingCost": 120.00,
            "paymentFee": 75.00,
            "netProfit": 474.00,
            "status": "computed",
        },
    }
}

# ---------------------------------------------------------------------------
# Inventory (internal + Shopify-style)
# ---------------------------------------------------------------------------
MOCK_INVENTORY_LIST = {
    "inventory": [
        {
            "id": "inv-1",
            "warehouseId": "wh-1",
            "warehouse": {"id": "wh-1", "name": "Main Warehouse", "city": "Bangalore", "state": "Karnataka"},
            "variantId": "pv-1",
            "variant": {
                "id": "pv-1",
                "sku": "SKU-001",
                "product": {"id": "p-1", "title": "Classic Tee", "brand": "LaCleo"},
            },
            "totalQty": 150,
            "reservedQty": 10,
            "availableQty": 140,
        },
        {
            "id": "inv-2",
            "warehouseId": "wh-1",
            "warehouse": {"id": "wh-1", "name": "Main Warehouse", "city": "Bangalore", "state": "Karnataka"},
            "variantId": "pv-2",
            "variant": {
                "id": "pv-2",
                "sku": "SKU-002",
                "product": {"id": "p-2", "title": "Cotton Socks", "brand": "LaCleo"},
            },
            "totalQty": 80,
            "reservedQty": 2,
            "availableQty": 78,
        },
        {
            "id": "inv-3",
            "warehouseId": "wh-1",
            "warehouse": {"id": "wh-1", "name": "Main Warehouse", "city": "Bangalore", "state": "Karnataka"},
            "variantId": "pv-3",
            "variant": {
                "id": "pv-3",
                "sku": "SKU-003",
                "product": {"id": "p-3", "title": "Summer Dress", "brand": "LaCleo"},
            },
            "totalQty": 25,
            "reservedQty": 1,
            "availableQty": 24,
        },
    ]
}

MOCK_SHOPIFY_INVENTORY = {
    "inventory": [
        {"sku": "SKU-001", "product_name": "Classic Tee Blue", "available": 140, "location_id": "loc-1"},
        {"sku": "SKU-002", "product_name": "Cotton Socks", "available": 78, "location_id": "loc-1"},
        {"sku": "SKU-003", "product_name": "Summer Dress", "available": 24, "location_id": "loc-1"},
    ],
    "warning": None,
}

# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
MOCK_ANALYTICS_SUMMARY = {
    "totalOrders": 42,
    "totalRevenue": 125000.00,
    "recentOrders": [
        {"id": _MOCK_ORDER_ID, "externalId": "SHOP-1001", "source": "SHOPIFY", "status": "CONFIRMED", "total": 2499.00, "createdAt": (_MOCK_NOW - timedelta(days=2)).isoformat() + "Z"},
        {"id": _MOCK_ORDER_ID_2, "externalId": "SHOP-1002", "source": "SHOPIFY", "status": "NEW", "total": 1899.00, "createdAt": (_MOCK_NOW - timedelta(days=1)).isoformat() + "Z"},
    ],
}

MOCK_PROFIT_SUMMARY = {
    "revenue": 125000.00,
    "netProfit": 28500.00,
    "marginPercent": 22.8,
    "lossCount": 3,
    "lossAmount": 2400.00,
    "rtoCount": 2,
    "rtoAmount": 1800.00,
    "lostCount": 1,
    "lostAmount": 600.00,
    "courierLossPercent": 4.2,
}

# ---------------------------------------------------------------------------
# Config / Integrations
# ---------------------------------------------------------------------------
MOCK_CONFIG_STATUS = {
    "integrations": [
        {"type": "SHOPIFY", "status": "CONNECTED", "name": "My Store"},
    ],
    "subscriptions": [],
}

MOCK_SHOPIFY_STATUS = {
    "connected": True,
    "shop_domain": "mock-store.myshopify.com",
}

MOCK_SYNC_JOBS = {
    "jobs": [
        {"id": "job-1", "job_type": "PULL_ORDERS", "status": "SUCCESS", "started_at": (_MOCK_NOW - timedelta(hours=1)).isoformat(), "records_processed": 15},
        {"id": "job-2", "job_type": "PUSH_INVENTORY", "status": "QUEUED", "started_at": None, "records_processed": 0},
    ],
}

# ---------------------------------------------------------------------------
# Integrations catalog (simplified)
# ---------------------------------------------------------------------------
MOCK_INTEGRATIONS_CATALOG = {
    "sections": [
        {
            "id": "stores",
            "title": "Stores",
            "description": "Connect your sales channels",
            "providers": [
                {"id": "shopify", "name": "Shopify", "icon": "🛍️", "description": "Connect via OAuth or API key"},
            ],
        },
        {
            "id": "logistics",
            "title": "Logistics & Supply Chain",
            "description": "Connect couriers and fulfillment",
            "providers": [
                {"id": "delhivery", "name": "Delhivery", "icon": "🚚"},
                {"id": "selloship", "name": "Selloship", "icon": "📦"},
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Webhooks / Workers (minimal)
# ---------------------------------------------------------------------------
MOCK_WEBHOOKS_LIST = []
MOCK_WEBHOOK_SUBSCRIPTIONS = []
MOCK_WORKERS_LIST = {"workers": [{"id": "order-sync", "name": "Order Sync", "status": "idle"}]}
