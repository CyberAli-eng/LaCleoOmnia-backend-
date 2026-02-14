#!/bin/bash
# Production deployment script with safe migration

echo "Starting deployment..."

# First, try to run the safe migration script
echo "Running safe migration..."
python3 safe_migrate.py

# If migration fails, try stamping to the latest head
if [ $? -ne 0 ]; then
    echo "Migration failed, attempting to stamp to latest head..."
    python3 -m alembic stamp final_merge_20240214
fi

# Start the application
echo "Starting application..."
python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT
