#!/bin/bash

# Safe migration script for production deployment
# This script handles multiple heads and ensures proper migration

echo "Starting safe migration process..."

# First, check current heads
echo "Checking current migration heads..."
python3 -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script_dir = ScriptDirectory.from_config(cfg)
heads = script_dir.get_heads()
print('Current heads:', heads)
if len(heads) > 1:
    print('Multiple heads detected, will merge...')
else:
    print('Single head detected, proceeding normally...')
"

# If there are multiple heads, upgrade to the latest merge
if python3 -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script_dir = ScriptDirectory.from_config(cfg)
heads = script_dir.get_heads()
exit(0 if len(heads) > 1 else 1)
"; then
    echo "Multiple heads detected, upgrading to final_merge_20240214..."
    python3 -m alembic upgrade final_merge_20240214
else
    echo "Single head detected, upgrading to head..."
    python3 -m alembic upgrade head
fi

echo "Migration completed successfully!"
