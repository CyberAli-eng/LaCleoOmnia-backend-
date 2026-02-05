#!/bin/bash

# Setup script for local PostgreSQL database
# This script helps set up PostgreSQL for local development

set -e

echo "🚀 Setting up local PostgreSQL database for LaCleoOmnia..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo -e "${RED}❌ PostgreSQL is not installed!${NC}"
    echo ""
    echo "Please install PostgreSQL:"
    echo "  macOS: brew install postgresql@14"
    echo "  Ubuntu: sudo apt-get install postgresql postgresql-contrib"
    echo "  Windows: Download from https://www.postgresql.org/download/"
    exit 1
fi

echo -e "${GREEN}✅ PostgreSQL is installed${NC}"

# Check if PostgreSQL is running
if ! pg_isready -q; then
    echo -e "${YELLOW}⚠️  PostgreSQL server is not running${NC}"
    echo ""
    echo "Starting PostgreSQL..."
    
    # Try to start PostgreSQL (macOS with Homebrew)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew services start postgresql@14 || brew services start postgresql
        else
            echo -e "${RED}Please start PostgreSQL manually:${NC}"
            echo "  brew services start postgresql@14"
            exit 1
        fi
    else
        echo -e "${RED}Please start PostgreSQL manually:${NC}"
        echo "  sudo systemctl start postgresql  # Linux"
        exit 1
    fi
    
    # Wait a bit for PostgreSQL to start
    sleep 2
fi

echo -e "${GREEN}✅ PostgreSQL is running${NC}"

# Database configuration
DB_NAME="lacleo_omnia"
DB_USER="admin"
DB_PASSWORD="password"

# Get current PostgreSQL user (usually your macOS username)
CURRENT_USER=$(whoami)

echo ""
echo "📊 Database Configuration:"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Password: $DB_PASSWORD"
echo ""

# Create database user if it doesn't exist
echo "Creating database user '$DB_USER'..."
psql -U "$CURRENT_USER" -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
    psql -U "$CURRENT_USER" -d postgres -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" || \
    echo -e "${YELLOW}⚠️  User might already exist, continuing...${NC}"

echo -e "${GREEN}✅ User created${NC}"

# Create database if it doesn't exist
echo "Creating database '$DB_NAME'..."
psql -U "$CURRENT_USER" -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
    psql -U "$CURRENT_USER" -d postgres -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || \
    echo -e "${YELLOW}⚠️  Database might already exist, continuing...${NC}"

echo -e "${GREEN}✅ Database created${NC}"

# Grant privileges
echo "Granting privileges..."
psql -U "$CURRENT_USER" -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" || true

echo -e "${GREEN}✅ Privileges granted${NC}"

echo ""
echo -e "${GREEN}🎉 Database setup complete!${NC}"
echo ""
echo "Connection string:"
echo "  postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo ""
echo "Add this to your .env file:"
echo "  DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
echo ""
echo "Next steps:"
echo "  1. Update your .env file with the DATABASE_URL above"
echo "  2. Run: python seed.py"
echo "  3. Start the API: python -m uvicorn main:app --reload"
echo ""
