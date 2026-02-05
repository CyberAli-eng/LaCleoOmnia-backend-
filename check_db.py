#!/usr/bin/env python3
"""
Quick database connection check script
"""
from sqlalchemy import text
from app.database import engine
from app.config import settings

def check_database():
    """Check if database connection works"""
    print("🔍 Checking database connection...")
    print(f"   Environment: {settings.ENV}")
    print(f"   Database URL: {settings.DATABASE_URL.split('@')[0]}@***")
    print("")
    
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print("✅ Database connection successful!")
            print(f"   PostgreSQL version: {version.split(',')[0]}")
            return True
    except Exception as e:
        print(f"❌ Database connection failed!")
        print(f"   Error: {e}")
        print("")
        print("💡 Troubleshooting:")
        print("   1. Check if PostgreSQL is running:")
        print("      pg_isready")
        print("")
        print("   2. Start PostgreSQL:")
        print("      macOS: brew services start postgresql@14")
        print("      Linux: sudo systemctl start postgresql")
        print("")
        print("   3. Run setup script:")
        print("      ./setup_local_db.sh")
        print("")
        print("   4. Check DATABASE_URL in .env file")
        return False

if __name__ == "__main__":
    success = check_database()
    exit(0 if success else 1)
