# LaCleoOmnia OMS - Python FastAPI Backend

## 🚀 Quick Start

### Local Development Setup

**For detailed local setup instructions, see:**
- **[README_LOCAL.md](./README_LOCAL.md)** - Quick setup guide
- **[LOCAL_SETUP.md](./LOCAL_SETUP.md)** - Detailed manual setup

### Quick Setup (Automated)

```bash
cd apps/api-python

# 1. Setup PostgreSQL database (creates user, database, grants permissions)
./setup_local_db.sh

# 2. Copy environment file
cp .env.example .env

# 3. Install dependencies
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# 4. Check database connection
python check_db.py

# 5. Seed database (creates tables + initial data)
python seed.py

# 6. Run server
python -m uvicorn main:app --reload
```

### Manual Setup

1. **Install PostgreSQL** (if not installed)
   ```bash
   # macOS
   brew install postgresql@14
   brew services start postgresql@14
   
   # Linux
   sudo apt-get install postgresql postgresql-contrib
   sudo systemctl start postgresql
   ```

2. **Create database** (or run `./setup_local_db.sh`)
   ```bash
   psql postgres
   CREATE USER admin WITH PASSWORD 'password';
   CREATE DATABASE lacleo_omnia OWNER admin;
   GRANT ALL PRIVILEGES ON DATABASE lacleo_omnia TO admin;
   \q
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and set DATABASE_URL=postgresql://admin:password@localhost:5432/lacleo_omnia
   ```

4. **Install dependencies and seed**
   ```bash
   pip install -r requirements.txt
   python seed.py
   ```

## 📁 Project Structure

```
apps/api-python/
├── app/
│   ├── __init__.py
│   ├── auth.py              # JWT & password auth
│   ├── config.py            # App config (env)
│   ├── database.py          # DB session, engine
│   ├── models/              # SQLAlchemy models (single package)
│   │   └── __init__.py      # User, Order, Channel, etc.
│   ├── http/                # HTTP layer
│   │   ├── controllers/     # Request handlers (ex-routers)
│   │   │   ├── auth.py, orders.py, channels.py, integrations.py, ...
│   │   └── requests/        # Pydantic schemas (validation)
│   │       ├── __init__.py
│   │       └── schemas.py
│   └── services/            # Business logic
│       ├── credentials.py, email_service.py, http_client.py
│       ├── shopify*.py, selloship_service.py, delhivery_service.py
│       ├── order_import.py, profit_calculator.py, shipment_sync.py
│       └── ad_spend_sync.py, sync_engine.py, ...
├── routes/
│   ├── __init__.py
│   └── api.py               # Central route registration (/api/*)
├── alembic/                 # Database migrations
├── main.py                  # FastAPI entry point
├── seed.py
├── requirements.txt
└── .env.example
```

See [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for flow and details.

## 🔑 API Endpoints

All endpoints are prefixed with `/api`

### Auth
- `POST /api/auth/login` - Login
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout

### Channels & Integrations
- `GET /api/channels` - List channels
- `GET /api/integrations/catalog` - Integration catalog (Shopify, Delhivery, Selloship, Meta/Google Ads)
- `GET /api/integrations/providers/{provider_id}/status` - Provider connection status
- `POST /api/integrations/providers/{provider_id}/connect` - Connect provider (e.g. delhivery, selloship)
- Shopify OAuth: `/auth/shopify/callback` (public), channels/shopify routes for connect/test/import

### Orders
- `GET /api/orders` - List orders
- `GET /api/orders/{id}` - Get order
- `POST /api/orders/{id}/confirm` - Confirm order
- `POST /api/orders/{id}/pack` - Pack order
- `POST /api/orders/{id}/ship` - Ship order
- `POST /api/orders/{id}/cancel` - Cancel order

### Inventory
- `GET /api/inventory` - List inventory
- `POST /api/inventory/adjust` - Adjust inventory

### Products
- `GET /api/products` - List products
- `POST /api/products` - Create product (Admin)
- `GET /api/products/{id}` - Get product
- `PATCH /api/products/{id}` - Update product (Admin)
- `DELETE /api/products/{id}` - Delete product (Admin)

### Warehouses
- `GET /api/warehouses` - List warehouses
- `POST /api/warehouses` - Create warehouse
- `PATCH /api/warehouses/{id}` - Update warehouse

### Shipments (Delhivery + Selloship)
- `GET /api/shipments` - List shipments
- `GET /api/shipments/order/{order_id}` - Get shipment by order
- `POST /api/shipments` - Create shipment (order_id, awb_number, courier_name, forward_cost, reverse_cost)
- `POST /api/shipments/sync` - Sync all active shipments (current user; uses ProviderCredential or env keys)
- `GET /api/shipments/{id}` - Get shipment

### Profit & SKU costs
- `GET /api/sku-costs` - List SKU costs
- `POST /api/sku-costs` - Create/update SKU cost
- `GET /api/profit/order/{order_id}` - Get profit for order
- `POST /api/profit/recompute` - Recompute profit (all or single order)

### Analytics
- `GET /api/analytics/summary` - Dashboard summary
- `GET /api/analytics/profit-summary` - Profit KPIs (revenue, net profit, margin, RTO/loss)

### Sync
- `GET /api/sync/jobs` - List sync jobs (when implemented)
- Workers: Shopify order/inventory sync; unified shipment sync (Delhivery + Selloship) every 30 min

## 🔐 Authentication

All endpoints (except `/api/auth/login`) require a Bearer token:

```
Authorization: Bearer <token>
```

## 📊 Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## 🧪 Testing

```bash
# Run with auto-reload
uvicorn main:app --reload --port 4000

# Access API docs
# http://localhost:4000/docs (Swagger UI)
# http://localhost:4000/redoc (ReDoc)
```

## 🔄 Migration from Node.js API

The Python backend is a complete replacement for the Express API:

- ✅ All routes ported
- ✅ Business logic preserved
- ✅ Same database schema
- ✅ Same API contract
- ✅ Authentication with JWT
- ✅ Role-based access control

Just update the frontend API URL to point to the Python backend!
