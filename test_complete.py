"""
Complete test of Shopify fulfilled orders issue
"""
import requests
import json

BASE_URL = 'https://lacleoomnia-api.onrender.com'

def test_complete_flow():
    """Test the complete flow"""
    print("=== Complete Shopify Fulfilled Orders Test ===")
    
    # Get token
    login_data = {'email': 'shaizqurashi12345@gmail.com', 'password': 'aligarh123boss'}
    response = requests.post(f'{BASE_URL}/api/auth/login', json=login_data)
    token = response.json().get('token')
    headers = {'Authorization': f'Bearer {token}'}
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.json()}")
        return
    
    print(f"✅ Login successful")
    
    # Test 1: Check current orders
    print("\\n📋 Test 1: Current Orders")
    response = requests.get(f'{BASE_URL}/api/orders', headers=headers)
    if response.status_code == 200:
        orders_data = response.json()
        orders = orders_data.get('orders', [])
        print(f"Current orders in DB: {len(orders)}")
        
        # Count statuses
        status_counts = {}
        for order in orders:
            status = order.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("Status breakdown:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
    else:
        print(f"❌ Failed to get orders: {response.json()}")
    
    # Test 2: Force sync to see if fulfilled orders come through
    print("\\n🔄 Test 2: Force Shopify Sync")
    response = requests.post(f'{BASE_URL}/api/integrations/shopify/sync/orders', headers=headers)
    if response.status_code == 200:
        sync_data = response.json()
        print(f"✅ Sync result: {sync_data}")
    else:
        print(f"❌ Sync failed: {response.json()}")
    
    # Test 3: Check orders after sync
    print("\\n📋 Test 3: Orders After Sync")
    response = requests.get(f'{BASE_URL}/api/orders', headers=headers)
    if response.status_code == 200:
        orders_data = response.json()
        orders = orders_data.get('orders', [])
        
        # Count statuses
        status_counts = {}
        for order in orders:
            status = order.get('status', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print(f"Orders after sync: {len(orders)}")
        print("Status breakdown:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
        
        # Look for shipped orders
        shipped_orders = [o for o in orders if o.get('status') in ['SHIPPED', 'FULFILLED']]
        print(f"\\n📦 Shipped orders: {len(shipped_orders)}")
        
        if shipped_orders:
            print("Sample shipped orders:")
            for i, order in enumerate(shipped_orders[:3]):
                print(f"  {i+1}. {order.get('channelOrderId')} - {order.get('status')}")
        else:
            print("❌ Still no shipped orders")
    else:
        print(f"❌ Failed to get orders after sync: {response.json()}")
    
    # Test 4: Check if there's a direct API to test Shopify connection
    print("\\n🔍 Test 4: Direct Shopify Status Check")
    response = requests.get(f'{BASE_URL}/api/integrations/shopify/status', headers=headers)
    if response.status_code == 200:
        shopify_data = response.json()
        print(f"Shopify connection: {shopify_data}")
    else:
        print(f"❌ Shopify status failed: {response.json()}")
    
    print("\\n🎯 Summary:")
    print("The issue appears to be that Shopify sync is not bringing in fulfilled orders.")
    print("This could be due to:")
    print("1. Shopify API permissions not including fulfilled orders")
    print("2. Fulfilled orders being filtered out somewhere")
    print("3. User account mismatch")
    print("4. Database schema issues")
    print("\\nNext steps:")
    print("1. Check Shopify Admin to confirm fulfilled orders exist")
    print("2. Verify API scopes include read_orders")
    print("3. Test Shopify API directly with fulfillment_status=fulfilled")

if __name__ == "__main__":
    test_complete_flow()
