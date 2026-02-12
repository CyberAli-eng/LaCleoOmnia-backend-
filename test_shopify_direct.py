"""
Test Shopify API directly to debug fulfilled orders issue
"""
import asyncio
import httpx
import os
from app.services.credentials import decrypt_token
from app.database import SessionLocal
from app.models import Channel, ChannelType, ChannelAccount

async def test_shopify_direct():
    """Test Shopify API directly"""
    print("=== Direct Shopify API Test ===")
    
    db = SessionLocal()
    
    try:
        # Get Shopify account
        channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
        if not channel:
            print("❌ Shopify channel not found")
            return
        
        account = db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == channel.id,
            ChannelAccount.user_id == "1",  # Try user ID 1
            ChannelAccount.shop_domain.isnot(None),
        ).first()
        
        if not account:
            print("❌ Shopify account not found")
            return
        
        print(f"✅ Account: {account.shop_domain}")
        
        # Decrypt token
        try:
            token = decrypt_token(account.access_token or "")
            print(f"✅ Token length: {len(token)}")
        except Exception as e:
            print(f"❌ Token error: {e}")
            return
        
        # Test different API calls
        base_url = f"https://{account.shop_domain}/admin/api/2024-01"
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }
        
        print("\\n📋 Test 1: All orders (status=any)")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/orders.json",
                params={"status": "any", "limit": 10},
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            orders = data.get("orders", [])
            print(f"Total orders: {len(orders)}")
            
            # Check fulfillment statuses
            statuses = {}
            for order in orders:
                status = order.get("fulfillment_status", "none")
                statuses[status] = statuses.get(status, 0) + 1
            
            print("Fulfillment status breakdown:")
            for status, count in statuses.items():
                print(f"  {status}: {count}")
        
        print("\\n📦 Test 2: Only fulfilled orders")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/orders.json",
                params={"status": "any", "limit": 10, "fulfillment_status": "fulfilled"},
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            orders = data.get("orders", [])
            print(f"Fulfilled orders: {len(orders)}")
            
            if orders:
                for i, order in enumerate(orders[:3]):
                    print(f"  {i+1}. {order.get('name')} - {order.get('fulfillment_status')}")
                    fulfillments = order.get('fulfillments', [])
                    if fulfillments:
                        for j, fulfillment in enumerate(fulfillments):
                            tracking = fulfillment.get('tracking_number')
                            print(f"       Tracking {j+1}: {tracking}")
        
        print("\\n📦 Test 3: Only unfulfilled orders")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/orders.json",
                params={"status": "any", "limit": 10, "fulfillment_status": "unfulfilled"},
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            orders = data.get("orders", [])
            print(f"Unfulfilled orders: {len(orders)}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_shopify_direct())
