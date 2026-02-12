"""
Check actual user ID in orders database
"""
from app.database import SessionLocal
from app.models import Order

def check_user_ids():
    """Check what user IDs are actually in the orders"""
    print("=== Checking User IDs in Orders ===")
    
    db = SessionLocal()
    
    try:
        # Get all unique user IDs from orders
        user_ids = db.query(Order.user_id).distinct().all()
        print(f"Found {len(user_ids)} unique user IDs:")
        
        for user_id_tuple in user_ids:
            user_id = user_id_tuple[0]
            print(f"  User ID: {user_id}")
        
        # Get first few orders with their user IDs
        orders = db.query(Order.id, Order.user_id, Order.channel_order_id).limit(5).all()
        print(f"\\nFirst 5 orders:")
        for order in orders:
            print(f"  Order {order.channel_order_id} -> User ID: {order.user_id}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        db.close()

if __name__ == "__main__":
    check_user_ids()
