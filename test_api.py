#!/usr/bin/env python3
"""
Test script to debug API authentication and data issues
"""
import requests
import json

# Your deployed API base URL
BASE_URL = "https://lacleoomnia-api.onrender.com"

def test_health():
    """Test health endpoint"""
    print("=== Testing Health Endpoint ===")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

def test_login():
    """Test login to get valid token"""
    print("\n=== Testing Login ===")
    try:
        # You'll need to provide your actual credentials
        login_data = {
            "email": "shaizqurashi12345@gmail.com",  # Replace with your email
            "password": "aligarh123boss"       # Replace with your password
        }
        response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            token = response.json().get("token")  # Changed from access_token to token
            print(f"Token: {token}")
            return token
    except Exception as e:
        print(f"Error: {e}")
    return None

def test_settlements(token):
    """Test settlements endpoint with valid token"""
    print("\n=== Testing Settlements ===")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/settlements", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

def test_webhooks_events(token):
    """Test webhooks events endpoint"""
    print("\n=== Testing Webhooks Events ===")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/webhooks/events", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

def test_integrations_status(token):
    """Test integrations status"""
    print("\n=== Testing Integrations Status ===")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/integrations/providers/shopify/status", headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Run all tests"""
    print("API Testing Script")
    print(f"Base URL: {BASE_URL}")
    
    test_health()
    
    # Test login with your credentials
    token = test_login()
    
    if token:
        print(f"\n✅ Successfully got token: {token[:50]}...")
        
        # Test authenticated endpoints
        test_settlements(token)
        test_webhooks_events(token)
        test_integrations_status(token)
    else:
        print("\n❌ Login failed - cannot test authenticated endpoints")

if __name__ == "__main__":
    main()
