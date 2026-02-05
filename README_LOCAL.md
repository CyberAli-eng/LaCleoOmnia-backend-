# Quick Local Setup

## Option 1: Automated Setup (Recommended)

```bash
cd apps/api-python

# 1. Setup database (creates user, database, grants permissions)
./setup_local_db.sh

# 2. Copy environment file
cp .env.example .env

# 3. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Seed database
python seed.py

# 5. Start server
python -m uvicorn main:app --reload
```

## Option 2: Docker Setup

```bash
cd apps/api-python

# 1. Start PostgreSQL in Docker
docker-compose -f docker-compose.local.yml up -d

# 2. Copy environment file
cp .env.example .env

# 3. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Seed database
python seed.py

# 5. Start server
python -m uvicorn main:app --reload
```

## Option 3: Manual Setup

See [LOCAL_SETUP.md](./LOCAL_SETUP.md) for detailed manual instructions.

## Verify Setup

1. **API Health:** http://localhost:8000/health
2. **API Docs:** http://localhost:8000/docs
3. **Login:** Use `admin@local` / `Admin@123`
4. **Shipments sync:** After connecting Delhivery/Selloship in Integrations, use `POST /api/shipments/sync` (with JWT) or rely on background sync every 30 min (if API keys are set in .env or UI).

## Troubleshooting

- **PostgreSQL not running:** `brew services start postgresql@14` (macOS)
- **User doesn't exist:** Run `./setup_local_db.sh` again
- **Connection refused:** Check if PostgreSQL is running: `pg_isready`

For more help, see [LOCAL_SETUP.md](./LOCAL_SETUP.md).
