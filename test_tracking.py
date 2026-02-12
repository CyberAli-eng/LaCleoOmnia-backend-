"""
Simple Tracking Test - Get tracking info from existing orders
"""
import requests

BASE_URL = 'https://lacleoomnia-api.onrender.com'

# Get token
login_data = {'email': 'shaizqurashi12345@gmail.com', 'password': 'aligarh123boss'}
response = requests.post(f'{BASE_URL}/api/auth/login', json=login_data)
token = response.json().get('token')
headers = {'Authorization': f'Bearer {token}'}

print('=== Manual Tracking Investigation ===')

# Get orders to see if any have tracking info
response = requests.get(f'{BASE_URL}/api/orders', headers=headers)
if response.status_code == 200:
    orders_data = response.json()
    orders = orders_data.get('orders', [])
    print(f'Total orders: {len(orders)}')
    
    # Check first few orders for any tracking-related data
    for i, order in enumerate(orders[:5]):
        print(f'\nOrder {i+1}: {order.get("channelOrderId")}')
        print(f'  Status: {order.get("status")}')
        print(f'  Payment: {order.get("paymentMode")}')
        print(f'  Total: {order.get("orderTotal")}')
        
        # Check if order has any shipment/fulfillment data
        if 'shipments' in order:
            shipments = order.get('shipments', [])
            print(f'  Shipments: {len(shipments)}')
            for shipment in shipments:
                courier = shipment.get('courier', 'Unknown')
                tracking = shipment.get('trackingNumber', 'No tracking')
                print(f'    • {courier} - {tracking}')
        else:
            print(f'  Shipments: None')

# Check if there are any shipments already
print('\n=== Existing Shipments ===')
response = requests.get(f'{BASE_URL}/api/shipments', headers=headers)
if response.status_code == 200:
    shipments_data = response.json()
    shipments = shipments_data.get('shipments', [])
    print(f'Existing shipments: {len(shipments)}')
    
    for i, shipment in enumerate(shipments[:5]):
        print(f'  {i+1}. {shipment.get("tracking_id", "N/A")} - {shipment.get("courier", "Unknown")} - {shipment.get("status", "N/A")}')

print('\n=== Test Shopify Fulfillment Directly ===')
# Try to get fulfillment info for a specific order
response = requests.get(f'{BASE_URL}/api/orders', headers=headers)
if response.status_code == 200:
    orders_data = response.json()
    orders = orders_data.get('orders', [])
    if orders:
        test_order = orders[0]
        channel_order_id = test_order.get('channelOrderId')
        print(f'Testing order: {channel_order_id}')
        
        # Try to get Shopify fulfillment data
        try:
            response = requests.post(f'{BASE_URL}/api/integrations/shopify/sync/orders', headers=headers)
            if response.status_code == 200:
                print('Shopify sync completed')
            else:
                print(f'Shopify sync error: {response.json()}')
        except Exception as e:
            print(f'Exception: {e}')
