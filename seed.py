"""
Database seed script
"""
import asyncio
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import User, UserRole, Channel, ChannelType, Warehouse
from app.auth import get_password_hash

def seed_database():
    """Seed the database with initial data"""
    db = SessionLocal()
    
    try:
        # Create admin user
        admin = db.query(User).filter(User.email == "admin@local").first()
        if not admin:
            admin = User(
                email="admin@local",
                name="Admin User",
                password_hash=get_password_hash("Admin@123"),
                role=UserRole.ADMIN
            )
            db.add(admin)
            print("✅ Created admin user: admin@local")
        else:
            print("✅ Admin user already exists")
        
        # Create staff user
        staff = db.query(User).filter(User.email == "staff@local").first()
        if not staff:
            staff = User(
                email="staff@local",
                name="Staff User",
                password_hash=get_password_hash("Staff@123"),
                role=UserRole.STAFF
            )
            db.add(staff)
            print("✅ Created staff user: staff@local")
        else:
            print("✅ Staff user already exists")
        
        # Create channels
        channels = [
            ChannelType.SHOPIFY,
            ChannelType.AMAZON,
            ChannelType.FLIPKART,
            ChannelType.MYNTRA
        ]
        
        for channel_type in channels:
            channel = db.query(Channel).filter(Channel.name == channel_type).first()
            if not channel:
                channel = Channel(name=channel_type, is_active=True)
                db.add(channel)
                print(f"✅ Created channel: {channel_type.value}")
            else:
                print(f"✅ Channel {channel_type.value} already exists")
        
        # Create default warehouse
        warehouse = db.query(Warehouse).filter(Warehouse.name == "Main Warehouse").first()
        if not warehouse:
            warehouse = Warehouse(
                name="Main Warehouse",
                city="Mumbai",
                state="Maharashtra"
            )
            db.add(warehouse)
            print("✅ Created warehouse: Main Warehouse")
        else:
            print("✅ Warehouse already exists")
        
        db.commit()
        print("\n🎉 Seeding completed!")
        print("\n📝 Login credentials:")
        print("   Admin: admin@local / Admin@123")
        print("   Staff: staff@local / Staff@123")
        
    except Exception as e:
        print(f"❌ Seeding failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    print("🌱 Starting database seeding...")
    print("")
    
    # Test database connection first
    try:
        print("🔌 Testing database connection...")
        with engine.connect() as conn:
            print("✅ Database connection successful!")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("")
        print("💡 Troubleshooting:")
        print("   1. Make sure PostgreSQL is running:")
        print("      macOS: brew services start postgresql@14")
        print("      Linux: sudo systemctl start postgresql")
        print("")
        print("   2. Run the setup script:")
        print("      ./setup_local_db.sh")
        print("")
        print("   3. Check your DATABASE_URL in .env file")
        print("      Should be: postgresql://admin:password@localhost:5432/lacleo_omnia")
        exit(1)
    
    print("")
    
    # Create tables
    try:
        print("📦 Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created!")
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        exit(1)
    
    print("")
    
    # Seed data
    seed_database()
