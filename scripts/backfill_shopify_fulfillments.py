#!/usr/bin/env python3
"""
Backfill Shopify Fulfillments Script

This script runs once to populate existing orders with Shopify fulfillment data.
It fetches fulfillments for all existing orders and stores them in the order_shipments table.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.database import get_db, DATABASE_URL
from app.models import Order, User
from app.services.shopify_fulfillment_service import sync_all_pending_fulfillments

logger = logging.getLogger(__name__)


def backfill_all_orders() -> Dict[str, Any]:
    """
    Backfill fulfillment data for all existing orders.
    
    Returns:
        Summary of backfill results
    """
    try:
        logger.info("Starting backfill of Shopify fulfillments for all existing orders")
        
        # Create database session
        engine = create_engine(DATABASE_URL)
        db = Session(engine)
        
        # Get all users who have orders
        users_with_orders = db.query(User).join(
            User.orders
        ).filter(
            User.orders.any()  # Users with at least one order
        ).distinct().all()
        
        total_users = len(users_with_orders)
        total_orders_processed = 0
        total_shipments_created = 0
        total_shipments_updated = 0
        failed_users = []
        
        logger.info(f"Found {total_users} users with orders")
        
        for user in users_with_orders:
            try:
                result = sync_all_pending_fulfillments(str(user.id), db)
                
                if result["success"]:
                    total_orders_processed += result["total_orders"]
                    total_shipments_created += result["synced"]
                    total_shipments_updated += result["updated"]
                    
                    logger.info(f"User {user.email}: {result['message']}")
                    print(f"✅ User {user.email}: {result['message']}")
                else:
                    failed_users.append({
                        "user_id": user.id,
                        "email": user.email,
                        "error": result["message"]
                    })
                    logger.error(f"User {user.email}: {result['message']}")
                    print(f"❌ User {user.email}: {result['message']}")
                    
            except Exception as e:
                failed_users.append({
                    "user_id": user.id,
                    "email": user.email,
                    "error": str(e)
                })
                logger.error(f"User {user.email}: Unexpected error - {e}")
                print(f"❌ User {user.email}: Unexpected error - {e}")
        
        db.close()
        
        # Summary
        summary = {
            "success": len(failed_users) == 0,
            "message": f"Backfilled {total_orders_processed} orders for {total_users} users: {total_shipments_created} new shipments, {total_shipments_updated} updated",
            "total_users": total_users,
            "total_orders_processed": total_orders_processed,
            "total_shipments_created": total_shipments_created,
            "total_shipments_updated": total_shipments_updated,
            "failed_users": failed_users,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        print(f"\n🎉 BACKFILL SUMMARY:")
        print(f"   Users processed: {total_users}")
        print(f"   Orders processed: {total_orders_processed}")
        print(f"   New shipments: {total_shipments_created}")
        print(f"   Updated shipments: {total_shipments_updated}")
        print(f"   Failed users: {len(failed_users)}")
        
        if failed_users:
            print(f"\n❌ FAILED USERS:")
            for user in failed_users:
                print(f"   - {user['email']}: {user['error']}")
        
        print(f"\n✅ Backfill completed at {summary['timestamp']}")
        
        return summary
        
    except Exception as e:
        error_msg = f"Backfill failed: {str(e)}"
        logger.error(error_msg)
        print(f"❌ {error_msg}")
        return {
            "success": False,
            "message": error_msg,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


def main():
    """Main entry point for the backfill script."""
    print("🚀 Starting Shopify Fulfillments Backfill")
    print("=" * 50)
    
    result = backfill_all_orders()
    
    if result["success"]:
        print("\n🎯 BACKFILL COMPLETED SUCCESSFULLY!")
        print("Your existing orders now have Shopify fulfillment data!")
    else:
        print("\n💥 BACKFILL FAILED!")
        print("Please check the logs and fix any errors.")
    
    print("=" * 50)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('backfill_shopify_fulfillments.log')
        ]
    )
    
    main()
