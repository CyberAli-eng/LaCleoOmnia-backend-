#!/usr/bin/env python3
"""
Script to add Selloship credentials to provider_credentials table for background workers.
Run this script to configure Selloship API credentials for the AWB sync worker.
"""

import sys
import json
from sqlalchemy.orm import Session
from app.config import settings
from app.models import ProviderCredential, User
from app.services.credentials import encrypt_token
from app.database import SessionLocal

def add_selloship_credentials():
    """Add Selloship credentials for system user"""
    
    db = SessionLocal()
    
    try:
        # Check if system user exists, create if not
        system_user = db.query(User).filter(User.email == "system@localhost").first()
        if not system_user:
            print("Creating system user...")
            from app.auth import get_password_hash
            system_user = User(
                id="system",
                email="system@localhost",
                name="System User",
                password_hash=get_password_hash("system_password_123")  # Dummy password for system user
            )
            db.add(system_user)
            db.commit()
            print("✅ System user created")
        
        # Get Selloship credentials from user input
        print("\n=== Selloship Credentials Setup ===")
        print("Using your authenticated token from Selloship...")
        
        # Use the actual token you received
        token = "token 6981e432dc924177012024263996"
        base_url = "https://selloship.com/api/lock_actvs/channels"
        
        print(f"Token: {token}")
        print(f"Base URL: {base_url}")
        
        # Create credentials JSON
        credentials = {
            "token": token,
            "base_url": base_url
        }
        
        # Encrypt credentials
        encrypted_creds = encrypt_token(json.dumps(credentials))
        
        # Check if credentials already exist
        existing = db.query(ProviderCredential).filter(
            ProviderCredential.user_id == "system",
            ProviderCredential.provider_id == "selloship"
        ).first()
        
        if existing:
            # Update existing credentials
            existing.value_encrypted = encrypted_creds
            print("✅ Updated existing Selloship credentials")
        else:
            # Create new credentials
            new_creds = ProviderCredential(
                id=str(uuid.uuid4()),
                user_id="system",
                provider_id="selloship",
                value_encrypted=encrypted_creds
            )
            db.add(new_creds)
            print("✅ Created new Selloship credentials")
        
        db.commit()
        
        # Verify credentials were added
        from app.services.credentials import get_provider_credentials
        test_creds = get_provider_credentials(db, "system", "selloship")
        
        if test_creds:
            print("\n✅ SUCCESS: Credentials verified in database!")
            print(f"   Base URL: {test_creds.get('base_url')}")
            print(f"   Token: {'*' * 20}{test_creds.get('token', '')[-4:] if len(test_creds.get('token', '')) > 4 else '****'}")
            return True
        else:
            print("\n❌ ERROR: Failed to verify credentials!")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    import uuid  # Import here to avoid circular imports
    
    print("🚀 Adding Selloship credentials for background workers...")
    print("This will configure credentials for user_id='system', provider_id='selloship'")
    
    success = add_selloship_credentials()
    
    if success:
        print("\n🎉 Setup complete! The AWB sync worker should now work.")
        print("   Restart your application to pick up the new credentials.")
    else:
        print("\n❌ Setup failed. Please check the error above.")
        sys.exit(1)
