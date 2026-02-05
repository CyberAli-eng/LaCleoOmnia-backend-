# Local Development Setup Guide

## Prerequisites

1. **PostgreSQL** - Database server
2. **Python 3.9+** - Python runtime
3. **Virtual Environment** - For Python dependencies

## Step 1: Install PostgreSQL

### macOS (using Homebrew)
```bash
brew install postgresql@14
# or
brew install postgresql
```

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
```

### Windows
Download and install from: https://www.postgresql.org/download/windows/

## Step 2: Start PostgreSQL

### macOS (Homebrew)
```bash
brew services start postgresql@14
# or
brew services start postgresql
```

### Linux (systemd)
```bash
sudo systemctl start postgresql
sudo systemctl enable postgresql  # Auto-start on boot
```

### Windows
PostgreSQL usually runs as a service. Check Services panel.

## Step 3: Setup Database (Automated)

Run the setup script:

```bash
cd apps/api-python
./setup_local_db.sh
```

This will:
- ✅ Check if PostgreSQL is installed
- ✅ Start PostgreSQL if not running
- ✅ Create database user `admin`
- ✅ Create database `lacleo_omnia`
- ✅ Grant necessary privileges

## Step 4: Setup Database (Manual)

If the script doesn't work, do it manually:

### Connect to PostgreSQL
```bash
# macOS/Linux - uses your current user
psql postgres

# Or as postgres user
sudo -u postgres psql
```

### Create User and Database
```sql
-- Create user
CREATE USER admin WITH PASSWORD 'password';

-- Create database
CREATE DATABASE lacleo_omnia OWNER admin;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE lacleo_omnia TO admin;

-- Exit
\q
```

## Step 5: Configure Environment

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Update `.env` with your database connection:
```env
ENV=DEV
DATABASE_URL=postgresql://admin:password@localhost:5432/lacleo_omnia
JWT_SECRET=dev-secret-key-change-in-production
ENCRYPTION_KEY=dev-encryption-key-32-chars!!
```

## Step 6: Install Python Dependencies

```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Step 7: Run Database Migrations

```bash
# Apply Alembic migrations (recommended for schema changes)
alembic upgrade head

# Seed initial data (admin user, channels, warehouse)
python seed.py
```

This will:
- Apply any pending migrations (e.g. orders.shipping_address, sync_jobs.completed_at, ad_spend_daily, shopify_inventory)
- Create/update tables and seed initial data

## Step 8: Start the API Server

```bash
# Development mode (auto-reload)
python -m uvicorn main:app --reload

# Or use the run script
./run.sh
```

The API will be available at: `http://localhost:8000`

## Step 9: Verify Setup

1. **Check API health:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Check API docs:**
   Open: http://localhost:8000/docs

3. **Test login:**
   - Email: `admin@local`
   - Password: `Admin@123`

## Troubleshooting

### "Connection refused" Error

**Problem:** PostgreSQL server is not running.

**Solution:**
```bash
# macOS
brew services start postgresql@14

# Linux
sudo systemctl start postgresql

# Check status
pg_isready
```

### "role 'admin' does not exist" Error

**Problem:** Database user doesn't exist.

**Solution:**
```bash
# Connect to PostgreSQL
psql postgres

# Create user
CREATE USER admin WITH PASSWORD 'password';
\q
```

### "database 'lacleo_omnia' does not exist" Error

**Problem:** Database doesn't exist.

**Solution:**
```bash
# Connect to PostgreSQL
psql postgres

# Create database
CREATE DATABASE lacleo_omnia OWNER admin;
\q
```

### "psql: command not found" Error

**Problem:** PostgreSQL client tools not in PATH.

**Solution:**
```bash
# macOS (Homebrew)
export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"
# or
export PATH="/usr/local/opt/postgresql@14/bin:$PATH"

# Add to ~/.zshrc or ~/.bashrc for persistence
echo 'export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"' >> ~/.zshrc
```

### Permission Denied Errors

**Problem:** User doesn't have proper permissions.

**Solution:**
```sql
-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE lacleo_omnia TO admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin;
```

## Alternative: Use Docker

If you prefer Docker:

```bash
# Start PostgreSQL in Docker
docker run --name lacleo-postgres \
  -e POSTGRES_USER=admin \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=lacleo_omnia \
  -p 5432:5432 \
  -d postgres:14

# Your DATABASE_URL will be:
# postgresql://admin:password@localhost:5432/lacleo_omnia
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `./setup_local_db.sh` | Automated database setup |
| `python seed.py` | Create tables and seed data |
| `python -m uvicorn main:app --reload` | Start API server |
| `psql postgres` | Connect to PostgreSQL |
| `pg_isready` | Check if PostgreSQL is running |
| `brew services list` | List Homebrew services (macOS) |

## Default Credentials

After running `seed.py`:
- **Admin:** `admin@local` / `Admin@123`
- **Staff:** `staff@local` / `Staff@123`

**⚠️ Change these in production!**
