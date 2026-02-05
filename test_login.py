#!/usr/bin/env python3
"""
Test login credentials and verify users exist
"""
from app.database import SessionLocal
from app.models import User
from app.auth import verify_password, get_password_hash

def test_users():
    """Test if users exist and passwords are correct"""
    db = SessionLocal()
    
    try:
        print("🔍 Checking users in database...")
        print("")
        
        # Check admin user
        admin = db.query(User).filter(User.email == "admin@local").first()
        if admin:
            print("✅ Admin user exists:")
            print(f"   Email: {admin.email}")
            print(f"   Name: {admin.name}")
            print(f"   Role: {admin.role.value}")
            
            # Test password
            test_password = "Admin@123"
            if verify_password(test_password, admin.password_hash):
                print(f"   ✅ Password '{test_password}' is correct")
            else:
                print(f"   ❌ Password '{test_password}' is INCORRECT")
                print(f"   Password hash: {admin.password_hash[:20]}...")
        else:
            print("❌ Admin user NOT FOUND")
            print("   Run: python seed.py")
        
        print("")
        
        # Check staff user
        staff = db.query(User).filter(User.email == "staff@local").first()
        if staff:
            print("✅ Staff user exists:")
            print(f"   Email: {staff.email}")
            print(f"   Name: {staff.name}")
            print(f"   Role: {staff.role.value}")
            
            # Test password
            test_password = "Staff@123"
            if verify_password(test_password, staff.password_hash):
                print(f"   ✅ Password '{test_password}' is correct")
            else:
                print(f"   ❌ Password '{test_password}' is INCORRECT")
        else:
            print("❌ Staff user NOT FOUND")
            print("   Run: python seed.py")
        
        print("")
        print("📝 Login Credentials:")
        print("   Admin: admin@local / Admin@123")
        print("   Staff: staff@local / Staff@123")
        print("")
        
        # List all users
        all_users = db.query(User).all()
        print(f"📊 Total users in database: {len(all_users)}")
        if all_users:
            print("   Users:")
            for user in all_users:
                print(f"     - {user.email} ({user.role.value})")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_users()
