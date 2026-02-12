"""
Find user ID from existing orders
"""
from app.database import SessionLocal
from app.models import Order, ChannelAccount

def find_user_from_orders():
    """Find user ID by tracing back from existing orders"""
    print("=== Finding User ID from Orders ===")
    
    db = SessionLocal()
    
    try:
        # Get first order
        order = db.query(Order).first()
        if not order:
            print("❌ No orders found")
            return
        
        print(f"✅ Found order: {order.channel_order_id}")
        print(f"User ID: {order.user_id}")
        print(f"Channel ID: {order.channel_id}")
        print(f"Channel Account ID: {order.channel_account_id}")
        
        return order.user_id
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    find_user_from_orders()
