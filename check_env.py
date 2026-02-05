#!/usr/bin/env python3
"""
Check and validate .env file configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

print("🔍 Checking .env file configuration...")
print("")

# Required variables
required_vars = {
    'ENV': 'DEV or PROD',
    'DATABASE_URL': 'PostgreSQL connection string',
    'JWT_SECRET': 'Secure random string',
}

# Optional but recommended
optional_vars = {
    'ENCRYPTION_KEY': '32-character encryption key',
    'HOST': 'Server host (auto-detected if not set)',
    'PORT': 'Server port (default: 8000)',
}

print("📋 Required Variables:")
print("-" * 50)
all_good = True
for var, description in required_vars.items():
    value = os.getenv(var)
    if value:
        # Mask sensitive values
        if 'SECRET' in var or 'PASSWORD' in var or 'KEY' in var:
            display_value = value[:10] + "..." if len(value) > 10 else "***"
        elif 'DATABASE_URL' in var:
            # Show only the connection part, mask password
            if '@' in value:
                parts = value.split('@')
                if len(parts) > 1:
                    display_value = parts[0].split(':')[0] + ":***@" + parts[1].split('/')[0] + "/" + parts[1].split('/')[-1] if '/' in parts[1] else parts[1]
                else:
                    display_value = "***"
            else:
                display_value = "***"
        else:
            display_value = value
        print(f"✅ {var:20} = {display_value}")
    else:
        print(f"❌ {var:20} = NOT SET")
        print(f"   Description: {description}")
        all_good = False

print("")
print("📋 Optional Variables:")
print("-" * 50)
for var, description in optional_vars.items():
    value = os.getenv(var)
    if value:
        if 'KEY' in var or 'SECRET' in var:
            display_value = value[:10] + "..." if len(value) > 10 else "***"
        else:
            display_value = value
        print(f"✅ {var:20} = {display_value}")
    else:
        print(f"⚪ {var:20} = (using default)")

print("")
if all_good:
    print("✅ All required variables are set!")
    print("")
    print("💡 Your configuration looks good!")
    print("   You can now:")
    print("   1. Test database: python check_db.py")
    print("   2. Start server: python -m uvicorn main:app --reload")
else:
    print("❌ Some required variables are missing!")
    print("")
    print("💡 Please set the missing variables in your .env file")
    print("   Example .env file:")
    print("   ENV=DEV")
    print("   DATABASE_URL=postgresql://admin:password@localhost:5432/lacleo_omnia")
    print("   JWT_SECRET=your-secure-random-secret")
    print("   ENCRYPTION_KEY=your-32-character-encryption-key!!")
