# API Project Structure

This document describes the layout of the LaCleoOmnia API (FastAPI) after the restructure. **API URLs and behavior are unchanged**; only internal organization was updated.

## Directory layout

```
apps/api-python/
├── app/                        # Main application package
│   ├── __init__.py
│   ├── auth.py                 # JWT, password hash, get_current_user
│   ├── config.py               # Settings from environment
│   ├── database.py             # Engine, SessionLocal, get_db
│   ├── mock_data.py            # Fixture data when MOCK_DATA=true
│   ├── models/
│   │   └── __init__.py         # All models & enums (User, Order, Channel, ...)
│   ├── http/
│   │   ├── __init__.py
│   │   ├── controllers/        # Route handlers (one file per domain)
│   │   │   ├── __init__.py
│   │   │   ├── analytics.py, audit.py, auth.py, channels.py, config.py
│   │   │   ├── integrations.py, inventory.py, labels.py, marketplaces.py
│   │   │   ├── mock.py, orders.py, products.py, profit.py, shipments.py
│   │   │   ├── sku_costs.py, sync.py, users.py, warehouses.py
│   │   │   ├── webhooks.py, workers.py
│   │   └── requests/
│   │       ├── __init__.py     # Re-exports schemas
│   │       └── schemas.py      # LoginRequest, OrderResponse, etc.
│   └── services/               # Business logic
│       ├── __init__.py
│       ├── credentials.py, email_service.py, http_client.py, warehouse_helper.py
│       ├── shopify.py, shopify_service.py, shopify_oauth.py, shopify_webhook_handler.py
│       ├── shopify_inventory_persist.py, selloship_service.py, delhivery_service.py
│       ├── order_import.py, profit_calculator.py, shipment_sync.py
│       ├── sync_engine.py, ad_spend_sync.py, meta_ads_service.py, google_ads_service.py
│       ├── amazon_service.py, flipkart_service.py, myntra_service.py
│       └── ...
├── routes/
│   ├── __init__.py
│   └── api.py                  # register_routes(app, settings) – mounts all /api/* routers
├── alembic/
│   ├── env.py, script.py.mako
│   └── versions/               # Migration scripts
├── docs/
│   ├── PASSWORD_RESET_EMAIL.md
│   └── PROJECT_STRUCTURE.md
├── scripts/
│   └── validate_profit.py
├── main.py                     # FastAPI app, CORS, register_routes, health, Shopify OAuth
├── seed.py, check_db.py, check_env.py, test_login.py
├── requirements.txt, alembic.ini, run.sh, runtime.txt
├── README.md, LOCAL_SETUP.md, DEPLOYMENT_NOTES.md
└── .env.example
```

## Request flow

1. **Request** → `main.py` (FastAPI app)
2. **Route** → `routes/api.py` has registered routers from `app.http.controllers.*` with prefix `/api`
3. **Controller** → e.g. `app/http/controllers/orders.py` – validates input via `app.http.requests.schemas`, uses `app.auth.get_current_user`, calls **Services**
4. **Services** → `app/services/*` – business logic, use **Models** and DB
5. **Models** → `app/models` – SQLAlchemy models
6. **Response** → returned by the controller (same as before)

## Imports

- Controllers: `from app.http.requests import ...` (schemas), `from app.models import ...`, `from app.auth import ...`, `from app.services.* import ...`
- Services: `from app.models import ...`, `from app.config import settings`
- `main.py`: `from routes.api import register_routes`, `from app.database import ...`, `from app.models import ...`, `from app.config import settings`

## API base URL

All API endpoints remain under **`/api`**. Postman and frontend can keep:

- Base URL: `http://localhost:8000` (or your deployment host)
- Auth: `POST /api/auth/login`
- Orders: `GET /api/orders`, `GET /api/orders/{id}`, etc.
- Same paths for integrations, webhooks, shipments, inventory, profit, and the rest.

No change to the Postman collection is required beyond ensuring `base_url` points to your API.

## Frontend integration (web app)

The Next.js frontend (`apps/web`) talks to this API using:

- **Base URL:** `API_BASE_URL` from `@/utils/api` = `http://localhost:8000/api` (or `NEXT_PUBLIC_API_BASE_URL` / `NEXT_PUBLIC_API_URL` in production).
- **Paths:** All `authFetch(path)` and `fetch(API_BASE_URL + path)` use paths **without** a leading `/api` (e.g. `authFetch("/orders")` → `GET /api/orders` on the backend).
- **Auth:** Token is sent as `Authorization: Bearer <token>`; login/register use `POST /api/auth/login`, `POST /api/auth/register`; forgot/reset use `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`.
- **Labels:** Print and invoice links use the backend URL: `${API_BASE_URL}/labels/{id}/print`, `${API_BASE_URL}/orders/{id}/invoice`, so they hit the Python API when those endpoints exist.

Backend route prefixes in `routes/api.py` match these expectations (e.g. `prefix="/api/auth"`, `prefix="/api/orders"`), so no frontend path changes are required after the restructure.
