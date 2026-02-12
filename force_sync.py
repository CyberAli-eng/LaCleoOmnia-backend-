"""
Force sync by bypassing duplicate checks
"""
import requests

BASE_URL = 'https://lacleoomnia-api.onrender.com'

def force_sync():
    """Force sync by bypassing duplicate prevention"""
    print("=== Force Sync Test ===")
    
    # Get token
    login_data = {'email': 'shaizqurashi12345@gmail.com', 'password': 'aligarh123boss'}
    response = requests.post(f'{BASE_URL}/api/auth/login', json=login_data)
    token = response.json().get('token')
    headers = {'Authorization': f'Bearer {token}'}
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.json()}")
        return
    
    print("✅ Login successful")
    
    # Try to force sync with a parameter to bypass duplicate checks
    sync_data = {"force_sync": True, "bypass_duplicates": True}
    
    response = requests.post(f'{BASE_URL}/api/integrations/shopify/sync/orders', headers=headers, json=sync_data)
    print(f"Force sync status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Force sync result: {result}")
    else:
        print(f"❌ Force sync failed: {response.json()}")

if __name__ == "__main__":
    force_sync()
