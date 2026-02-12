"""
Simple test to get user ID
"""
from app.database import SessionLocal
from app.models import Order

def get_user_id():
    """Get user ID from first order"""
    print("=== Getting User ID ===")
    
    db = SessionLocal()
    
    try:
        # Get first order with minimal columns
        order = db.query(Order.id, Order.user_id, Order.channel_order_id).first()
        if not order:
            print("❌ No orders found")
            return None
        
        print(f"✅ User ID: {order.user_id}")
        print(f"✅ Order ID: {order.channel_order_id}")
        return order.user_id
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    get_user_id()
