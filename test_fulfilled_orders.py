"""
Quick test to fetch fulfilled orders from Shopify directly
"""
import asyncio
import httpx
from app.services.shopify import ShopifyService
from app.http.controllers.integrations import _get_shopify_integration
from app.database import SessionLocal
from app.auth import User

async def test_fulfilled_orders():
    """Test fetching fulfilled orders directly"""
    print("=== Testing Direct Shopify Fulfilled Orders Fetch ===")
    
    # Get database session
    db = SessionLocal()
    
    try:
        # Get a test user (you)
        user = db.query(User).filter(User.email == "shaizqurashi12345@gmail.com").first()
        if not user:
            print("❌ User not found")
            return
        
        print(f"✅ Found user: {user.email}")
        
        # Get Shopify integration
        shopify_integration = _get_shopify_integration(db, user)
        if not shopify_integration:
            print("❌ Shopify integration not found")
            return
        
        print(f"✅ Shopify integration found: {shopify_integration.shop_domain}")
        
        # Initialize Shopify service
        shopify_service = ShopifyService(shopify_integration)
        
        # Test 1: Get all orders (any status)
        print("\\n📋 Test 1: Get all orders (status=any)")
        all_orders = await shopify_service.get_orders(limit=50, fulfillment_status="any")
        print(f"Total orders: {len(all_orders)}")
        
        # Show status breakdown
        status_counts = {}
        for order in all_orders:
            status = order.get("fulfillment_status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("Status breakdown:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
        
        # Test 2: Get only fulfilled orders
        print("\\n📦 Test 2: Get only fulfilled orders")
        fulfilled_orders = await shopify_service.get_fulfilled_orders(limit=50)
        print(f"Fulfilled orders: {len(fulfilled_orders)}")
        
        # Show fulfilled orders with tracking
        if fulfilled_orders:
            print("\\n📋 Fulfilled orders with tracking:")
            for i, order in enumerate(fulfilled_orders[:5]):
                print(f"  {i+1}. Order {order.get('name')} - Status: {order.get('fulfillment_status')}")
                
                # Get fulfillments for this order
                fulfillments = await shopify_service.get_fulfillments(order.get('id'))
                for j, fulfillment in enumerate(fulfillments):
                    tracking = fulfillment.get('tracking_number')
                    company = fulfillment.get('tracking_company')
                    print(f"     Fulfillment {j+1}: {tracking} ({company})")
        else:
            print("❌ No fulfilled orders found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_fulfilled_orders())
