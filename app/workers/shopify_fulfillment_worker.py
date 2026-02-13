"""
Shopify Fulfillment Worker

Runs every 10 minutes to sync Shopify fulfillments for orders that don't have shipments yet.
This worker ensures real-time tracking data is available for fulfilled orders.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.shopify_fulfillment_service import sync_all_pending_fulfillments

logger = logging.getLogger(__name__)


class ShopifyFulfillmentWorker:
    """Worker for syncing Shopify fulfillments every 10 minutes."""
    
    def __init__(self):
        self.name = "shopify_fulfillment_worker"
        self.interval = 600  # 10 minutes in seconds
    
    def run_sync_cycle(self) -> Dict[str, Any]:
        """
        Run a single sync cycle for all users.
        
        Returns:
            Summary of sync results across all users
        """
        try:
            db = next(get_db())
            
            # Get all active users with Shopify integrations
            users_with_shopify = db.query(User).join(
                User.channel_accounts
            ).join(
                User.channel_accounts, User.channel_accounts.channel
            ).filter(
                # This is a simplified filter - in production you'd filter by channel type
                User.channel_accounts.any()  # Users with at least one channel account
            ).all()
            
            total_users = len(users_with_shopify)
            total_synced = 0
            total_updated = 0
            failed_users = []
            
            logger.info(f"Starting fulfillment sync for {total_users} users")
            
            for user in users_with_shopify:
                try:
                    result = sync_all_pending_fulfillments(str(user.id), db)
                    
                    if result["success"]:
                        total_synced += result["synced"]
                        total_updated += result["updated"]
                        logger.info(f"User {user.email}: {result['message']}")
                    else:
                        failed_users.append({
                            "user_id": user.id,
                            "email": user.email,
                            "error": result["message"]
                        })
                        logger.error(f"User {user.email}: {result['message']}")
                        
                except Exception as e:
                    failed_users.append({
                        "user_id": user.id,
                        "email": user.email,
                        "error": str(e)
                    })
                    logger.error(f"User {user.email}: Unexpected error - {e}")
            
            db.close()
            
            return {
                "success": len(failed_users) == 0,
                "message": f"Processed {total_users} users: {total_synced} new, {total_updated} updated shipments",
                "total_users": total_users,
                "total_synced": total_synced,
                "total_updated": total_updated,
                "failed_users": failed_users,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Fulfillment worker cycle failed: {e}")
            return {
                "success": False,
                "message": f"Worker cycle failed: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def run_single_sync(self) -> Dict[str, Any]:
        """
        Run a single sync cycle (called by scheduler).
        
        Returns:
            Sync result
        """
        logger.info("Starting Shopify fulfillment sync cycle")
        result = self.run_sync_cycle()
        
        if result["success"]:
            logger.info(f"Fulfillment sync completed: {result['message']}")
        else:
            logger.error(f"Fulfillment sync failed: {result['message']}")
        
        return result


def run_shopify_fulfillment_worker() -> Dict[str, Any]:
    """
    Entry point for the Shopify fulfillment worker.
    
    Returns:
        Sync result
    """
    worker = ShopifyFulfillmentWorker()
    return worker.run_single_sync()


if __name__ == "__main__":
    # For testing purposes
    result = run_shopify_fulfillment_worker()
    print(f"Worker result: {result}")
