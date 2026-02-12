"""
Test specific fulfilled order from your Shopify dashboard
"""
import requests
import asyncio
from app.services.shopify import ShopifyService
from app.services.shopify_service import get_orders_raw
from app.services.credentials import decrypt_token
from app.database import SessionLocal
from app.models import Channel, ChannelType, ChannelAccount

async def test_specific_order():
    """Test the specific order you mentioned: 14344960491918"""
    print("=== Testing Specific Fulfilled Order ===")
    
    db = SessionLocal()
    
    try:
        # Get Shopify account
        channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
        if not channel:
            print("❌ Shopify channel not found")
            return
        
        account = db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == channel.id,
            ChannelAccount.user_id == "1",  # Try your user ID
            ChannelAccount.shop_domain.isnot(None),
        ).first()
        
        if not account:
            print("❌ Shopify account not found")
            return
        
        print(f"✅ Using account: {account.shop_domain}")
        
        # Initialize Shopify service
        shopify_service = ShopifyService(account)
        
        # Test 1: Get all orders and search for tracking number
        print("\\n📋 Searching for tracking number 14344960491918...")
        all_orders = await shopify_service.get_orders(limit=100, fulfillment_status="any")
        
        found_order = None
        for order in all_orders:
            # Check fulfillments for tracking number
            fulfillments = order.get('fulfillments', [])
            for fulfillment in fulfillments:
                tracking_num = fulfillment.get('tracking_number')
                if tracking_num == '14344960491918':
                    found_order = order
                    print(f"✅ Found order with tracking!")
                    print(f"   Order ID: {order.get('id')}")
                    print(f"   Order Name: {order.get('name')}")
                    print(f"   Status: {order.get('fulfillment_status')}")
                    print(f"   Financial: {order.get('financial_status')}")
                    print(f"   Tracking: {tracking_num}")
                    print(f"   Customer: {order.get('customer', {}).get('first_name', '')} {order.get('customer', {}).get('last_name', '')}")
                    break
        
        if not found_order:
            print("❌ Order with tracking 14344960491918 not found")
            print("\\n📋 All tracking numbers found:")
            for order in all_orders:
                fulfillments = order.get('fulfillments', [])
                for fulfillment in fulfillments:
                    tracking_num = fulfillment.get('tracking_number')
                    if tracking_num:
                        print(f"   {tracking_num}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_specific_order())
