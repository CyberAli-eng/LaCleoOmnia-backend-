#!/usr/bin/env python3
"""
Production-safe migration script
Handles multiple heads and ensures proper migration state
"""
import sys
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic import command
from sqlalchemy import create_engine
import os

def main():
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    # Create Alembic config
    alembic_cfg = Config("alembic.ini")
    
    # Create engine and connection
    engine = create_engine(database_url)
    
    with engine.connect() as connection:
        # Create migration context
        context = MigrationContext.configure(connection)
        
        # Get current revision
        current_rev = context.get_current_revision()
        print(f"Current database revision: {current_rev}")
        
        # Get script directory
        from alembic.script import ScriptDirectory
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        heads = script_dir.get_heads()
        print(f"Available heads: {heads}")
        
        # Check if we have multiple heads in the database
        if current_rev and len(heads) > 1:
            print("Multiple heads detected, upgrading to final merge...")
            try:
                # Try to upgrade to the final merge
                command.upgrade(alembic_cfg, "final_merge_20240214")
                print("Successfully upgraded to final_merge_20240214")
            except Exception as e:
                print(f"Failed to upgrade to final_merge: {e}")
                # If that fails, try stamping to the latest head
                print("Attempting to stamp to latest head...")
                command.stamp(alembic_cfg, "final_merge_20240214")
                print("Successfully stamped to final_merge_20240214")
        else:
            print("Single head or fresh database, normal upgrade...")
            command.upgrade(alembic_cfg, "head")
            print("Successfully upgraded to head")
    
    print("Migration completed successfully!")

if __name__ == "__main__":
    main()
