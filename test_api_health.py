"""
Test deployed API health and authentication
"""
import requests
import json

BASE_URL = 'https://lacleoomnia-api.onrender.com'

def test_api_health():
    """Test API health and authentication issues"""
    print("=== API Health Check ===")
    
    try:
        # Test 1: Basic health endpoint (if exists)
        print("Testing basic health...")
        try:
            response = requests.get(f'{BASE_URL}/health', timeout=10)
            print(f"Health endpoint: {response.status_code}")
        except:
            print("Health endpoint not available")
        
        # Test 2: Login with fresh credentials
        print("\\nTesting authentication...")
        login_data = {'email': 'shaizqurashi12345@gmail.com', 'password': 'aligarh123boss'}
        response = requests.post(f'{BASE_URL}/api/auth/login', json=login_data, timeout=10)
        print(f"Login status: {response.status_code}")
        
        if response.status_code == 200:
            token_data = response.json()
            token = token_data.get('token')
            print("✅ Login successful, got token")
            
            # Test 3: Use token to access protected endpoint
            print("\\nTesting protected endpoint access...")
            headers = {'Authorization': f'Bearer {token}'}
            
            # Test orders endpoint
            response = requests.get(f'{BASE_URL}/api/orders', headers=headers, timeout=10)
            print(f"Orders endpoint: {response.status_code}")
            
            if response.status_code == 200:
                orders_data = response.json()
                orders = orders_data.get('orders', [])
                print(f"✅ Orders endpoint working: {len(orders)} orders")
            else:
                print(f"❌ Orders endpoint failed: {response.status_code}")
                if response.status_code == 401:
                    print("❌ Authentication failed - token invalid or expired")
                try:
                    error_detail = response.json()
                    print(f"Error detail: {error_detail}")
                except:
                    pass
            
            # Test 4: Check token expiration
            print("\\nTesting token validation...")
            try:
                # Decode token to check payload
                import base64
                import json
                from jose import jwt
                
                # Split token to get payload part
                token_parts = token.split('.')
                if len(token_parts) >= 2:
                    payload_b64 = token_parts[1]
                    payload_bytes = base64.urlsafe_b64decode(payload_b64 + '==')
                    payload_json = json.loads(payload_bytes.decode('utf-8'))
                    print(f"Token payload: {payload_json}")
                    
                    # Check expiration
                    import datetime
                    exp = payload_json.get('exp')
                    if exp:
                        exp_datetime = datetime.fromtimestamp(exp)
                        now = datetime.utcnow()
                        print(f"Token expires: {exp_datetime}")
                        print(f"Current time: {now}")
                        print(f"Token valid: {exp_datetime > now}")
                
            except Exception as e:
                print(f"Token validation error: {e}")
                
        else:
            print(f"❌ Login failed: {response.status_code}")
            try:
                error_detail = response.json()
                print(f"Login error: {error_detail}")
            except:
                pass
                
    except Exception as e:
        print(f"❌ Health check failed: {e}")

if __name__ == "__main__":
    test_api_health()
