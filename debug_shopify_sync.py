"""
Debug Shopify sync to see why fulfilled orders aren't coming through
"""
import requests
import asyncio
from app.services.shopify_service import get_orders_raw
from app.services.credentials import decrypt_token
from app.database import SessionLocal
from app.models import Channel, ChannelType, ChannelAccount

def debug_shopify_sync():
    """Debug the Shopify sync process"""
    print("=== Debugging Shopify Sync ===")
    
    db = SessionLocal()
    
    try:
        # Get Shopify channel
        channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
        if not channel:
            print("❌ Shopify channel not found")
            return
        
        print(f"✅ Shopify channel found: {channel.id}")
        
        # Get user's Shopify account
        account = db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == channel.id,
            ChannelAccount.user_id == "1",  # Your user ID might be different
            ChannelAccount.shop_domain.isnot(None),
        ).first()
        
        if not account:
            print("❌ Shopify account not found")
            return
        
        print(f"✅ Shopify account found: {account.shop_domain}")
        
        # Try to decrypt token
        try:
            token = decrypt_token(account.access_token or "")
            print(f"✅ Token decrypted successfully: {len(token)} chars")
        except Exception as e:
            print(f"❌ Token decryption failed: {e}")
            return
        
        # Test direct API call
        print("\\n📋 Testing direct Shopify API call...")
        try:
            import asyncio
            orders = asyncio.run(get_orders_raw(
                account.shop_domain,
                token,
                limit=50
            ))
            print(f"✅ Got {len(orders)} orders from Shopify")
            
            # Analyze orders
            status_counts = {}
            for order in orders:
                status = order.get("fulfillment_status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
                
            print("\\n📊 Order status breakdown:")
            for status, count in status_counts.items():
                print(f"  {status}: {count}")
            
            # Show some sample orders
            print("\\n📋 Sample orders:")
            for i, order in enumerate(orders[:5]):
                print(f"  {i+1}. {order.get('name')} - Status: {order.get('fulfillment_status')} - Financial: {order.get('financial_status')}")
                
                # Check for fulfillments
                if 'fulfillments' in order:
                    print(f"     Has {len(order['fulfillments'])} fulfillments")
                    for j, fulfillment in enumerate(order['fulfillments']):
                        tracking = fulfillment.get('tracking_number')
                        print(f"       Fulfillment {j+1}: {tracking}")
                else:
                    print("     No fulfillments field")
                    
        except Exception as e:
            print(f"❌ API call failed: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    debug_shopify_sync()
