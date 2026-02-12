"""
Test fulfilled orders with correct user ID
"""
import requests

BASE_URL = 'https://lacleoomnia-api.onrender.com'

# Get token
login_data = {'email': 'shaizqurashi12345@gmail.com', 'password': 'aligarh123boss'}
response = requests.post(f'{BASE_URL}/api/auth/login', json=login_data)
token = response.json().get('token')
headers = {'Authorization': f'Bearer {token}'}

print('=== Testing with User ID from Orders ===')

# Get orders to see user ID pattern
response = requests.get(f'{BASE_URL}/api/orders', headers=headers)
if response.status_code == 200:
    orders_data = response.json()
    orders = orders_data.get('orders', [])
    print(f'Total orders: {len(orders)}')
    
    if orders:
        # Try to extract user ID from first order
        first_order = orders[0]
        print(f'First order data keys: {list(first_order.keys())}')
        print(f'First order sample: {first_order}')
        
        # Test with hardcoded user ID "1" (common default)
        print('\\n📋 Testing fulfilled orders endpoint directly...')
        
        # Create a simple test endpoint call
        test_data = {
            "test": "fulfilled_orders",
            "user_id": "test_user_123"
        }
        
        response = requests.post(f'{BASE_URL}/api/integrations/shopify/sync/orders', headers=headers, json=test_data)
        print(f'Test sync status: {response.status_code}')
        if response.status_code != 200:
            print(f'Error: {response.json()}')

print('\\n=== Checking if deployment is working ===')
response = requests.get(f'{BASE_URL}/api/health', headers=headers)
print(f'Health check: {response.status_code}')
if response.status_code == 200:
    health_data = response.json()
    print(f'Health: {health_data}')
else:
    print(f'Health error: {response.json()}')
