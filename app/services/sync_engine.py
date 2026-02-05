"""
Advanced sync engine for order and inventory synchronization.
Uses shopify_service (full inventory pipeline) and shared persistence for inventory.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import (
    ChannelAccount,
    SyncJob,
    SyncJobStatus,
    SyncJobType,
    SyncLog,
    LogLevel,
    ShopifyIntegration,
)
from app.services.shopify import ShopifyService
from app.services.shopify_service import get_inventory as shopify_get_inventory
from app.services.shopify_inventory_persist import persist_shopify_inventory
from app.services.order_import import (
    import_shopify_orders,
    import_amazon_orders,
    import_flipkart_orders,
    import_myntra_orders,
)

logger = logging.getLogger(__name__)


class SyncEngine:
    """Background sync engine for automated reconciliation"""

    def __init__(self, db: Session):
        self.db = db

    async def sync_orders(self, account: ChannelAccount, limit: int = 250) -> dict:
        """Sync orders from channel."""
        sync_job = SyncJob(
            channel_account_id=account.id,
            job_type=SyncJobType.PULL_ORDERS,
            status=SyncJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_job)
        self.db.commit()
        self.db.refresh(sync_job)

        try:
            channel_name = account.channel.name.value if hasattr(account.channel.name, "value") else str(account.channel.name)
            if channel_name == "SHOPIFY":
                result = await import_shopify_orders(self.db, account)
            elif channel_name == "AMAZON":
                result = await import_amazon_orders(self.db, account)
            elif channel_name == "FLIPKART":
                result = await import_flipkart_orders(self.db, account)
            elif channel_name == "MYNTRA":
                result = await import_myntra_orders(self.db, account)
            else:
                raise ValueError(f"Unsupported channel: {channel_name}")

            sync_job.status = SyncJobStatus.SUCCESS
            sync_job.finished_at = datetime.now(timezone.utc)
            sync_job.records_processed = result.get("imported", 0)
            sync_job.records_failed = result.get("errors", 0) or result.get("failed", 0)

            log = SyncLog(
                sync_job_id=sync_job.id,
                level=LogLevel.INFO,
                message=f"Order sync completed: {result.get('imported', 0)} imported, {result.get('errors', result.get('failed', 0))} errors",
            )
            self.db.add(log)

            self.db.commit()
            return {
                "success": True,
                "jobId": sync_job.id,
                "imported": sync_job.records_processed,
                "failed": sync_job.records_failed,
            }
        except Exception as e:
            sync_job.status = SyncJobStatus.FAILED
            sync_job.finished_at = datetime.now(timezone.utc)
            sync_job.error_message = str(e)
            log = SyncLog(
                sync_job_id=sync_job.id,
                level=LogLevel.ERROR,
                message=f"Order sync failed: {str(e)}",
                raw_payload={"error": str(e)},
            )
            self.db.add(log)
            self.db.commit()
            return {"success": False, "jobId": sync_job.id, "error": str(e)}

    async def sync_inventory(self, account: ChannelAccount) -> dict:
        """
        Sync inventory from Shopify using full pipeline (products → variants → locations → levels)
        and persist to ShopifyInventory cache + Inventory table. Uses ShopifyIntegration token.
        """
        sync_job = SyncJob(
            channel_account_id=account.id,
            job_type=SyncJobType.PULL_PRODUCTS,
            status=SyncJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_job)
        self.db.commit()
        self.db.refresh(sync_job)

        try:
            if account.channel.name.value != "SHOPIFY":
                raise ValueError(f"Unsupported channel: {account.channel.name.value}")

            integration = (
                self.db.query(ShopifyIntegration)
                .filter(ShopifyIntegration.shop_domain == account.shop_domain)
                .first()
            )
            if not integration or not integration.access_token:
                raise ValueError(
                    "Shopify not connected for this account. Connect via OAuth and ensure ShopifyIntegration exists."
                )

            inv_list = await shopify_get_inventory(
                integration.shop_domain,
                integration.access_token,
            )
            inventory_synced = persist_shopify_inventory(
                self.db, integration.shop_domain, inv_list or []
            )

            sync_job.status = SyncJobStatus.SUCCESS
            sync_job.finished_at = datetime.now(timezone.utc)
            sync_job.records_processed = len(inv_list or [])
            sync_job.records_failed = 0

            log = SyncLog(
                sync_job_id=sync_job.id,
                level=LogLevel.INFO,
                message=f"Inventory sync completed: {len(inv_list or [])} items from Shopify, {inventory_synced} inventory records updated",
            )
            self.db.add(log)
            self.db.commit()

            return {
                "success": True,
                "jobId": sync_job.id,
                "synced": sync_job.records_processed,
                "inventory_records_updated": inventory_synced,
            }
        except Exception as e:
            sync_job.status = SyncJobStatus.FAILED
            sync_job.finished_at = datetime.now(timezone.utc)
            sync_job.error_message = str(e)
            log = SyncLog(
                sync_job_id=sync_job.id,
                level=LogLevel.ERROR,
                message=f"Inventory sync failed: {str(e)}",
                raw_payload={"error": str(e)},
            )
            self.db.add(log)
            self.db.commit()
            logger.warning("Inventory sync failed: %s", e)
            return {"success": False, "jobId": sync_job.id, "error": str(e)}
    
    async def daily_reconciliation(self, account: ChannelAccount) -> dict:
        """Daily full reconciliation - sync all orders and inventory"""
        results = {
            "orders": None,
            "inventory": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Sync orders
        try:
            results["orders"] = await self.sync_orders(account, limit=1000)
        except Exception as e:
            results["orders"] = {"success": False, "error": str(e)}
        
        # Sync inventory
        try:
            results["inventory"] = await self.sync_inventory(account)
        except Exception as e:
            results["inventory"] = {"success": False, "error": str(e)}
        
        return results
    
    def get_sync_history(self, account_id: str, limit: int = 50) -> list:
        """Get sync job history for an account"""
        jobs = self.db.query(SyncJob).filter(
            SyncJob.channel_account_id == account_id
        ).order_by(SyncJob.started_at.desc()).limit(limit).all()
        
        return [
            {
                "id": job.id,
                "jobType": job.job_type.value,
                "status": job.status.value,
                "startedAt": job.started_at.isoformat() if job.started_at else None,
                "completedAt": job.finished_at.isoformat() if job.finished_at else None,
                "recordsProcessed": job.records_processed,
                "recordsFailed": job.records_failed,
                "errorMessage": job.error_message
            }
            for job in jobs
        ]
