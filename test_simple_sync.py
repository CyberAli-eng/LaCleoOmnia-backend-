"""
Simple test to debug Shopify sync issue
"""
import requests

BASE_URL = 'https://lacleoomnia-api.onrender.com'

def test_simple_sync():
    """Test simple sync without complex logic"""
    print("=== Simple Shopify Sync Test ===")
    
    # Get token
    login_data = {'email': 'shaizqurashi12345@gmail.com', 'password': 'aligarh123boss'}
    response = requests.post(f'{BASE_URL}/api/auth/login', json=login_data)
    token = response.json().get('token')
    headers = {'Authorization': f'Bearer {token}'}
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.json()}")
        return
    
    print("✅ Login successful")
    
    # Test 1: Check current orders
    print("\\n📋 Current Orders:")
    response = requests.get(f'{BASE_URL}/api/orders', headers=headers)
    if response.status_code == 200:
        orders_data = response.json()
        orders = orders_data.get('orders', [])
        print(f"Total orders in DB: {len(orders)}")
        
        # Show first few orders
        for i, order in enumerate(orders[:3]):
            print(f"  {i+1}. {order.get('channelOrderId')} - {order.get('status')} - {order.get('paymentMode')}")
    
    # Test 2: Try to get Shopify status
    print("\\n🔍 Shopify Status:")
    response = requests.get(f'{BASE_URL}/api/integrations/shopify/status', headers=headers)
    if response.status_code == 200:
        shopify_data = response.json()
        print(f"Shopify connected: {shopify_data}")
    else:
        print(f"Shopify status failed: {response.json()}")
    
    # Test 3: Manual sync with minimal data
    print("\\n🔄 Manual Sync Test:")
    sync_data = {
        "test": True,
        "debug": True
    }
    
    response = requests.post(f'{BASE_URL}/api/integrations/shopify/sync/orders', headers=headers, json=sync_data)
    print(f"Manual sync status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Manual sync result: {result}")
    else:
        print(f"❌ Manual sync failed: {response.json()}")

if __name__ == "__main__":
    test_simple_sync()
