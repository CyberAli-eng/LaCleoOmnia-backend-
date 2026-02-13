"""
Worker Scheduler Configuration

Registers and schedules background workers for Shopify fulfillment sync and Selloship status enrichment.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from app.workers.shopify_fulfillment_worker import run_shopify_fulfillment_worker
from app.workers.selloship_status_worker import run_selloship_status_worker

logger = logging.getLogger(__name__)


class WorkerScheduler:
    """Scheduler for running background workers at specified intervals."""
    
    def __init__(self):
        self.workers = {
            "shopify_fulfillment": {
                "func": run_shopify_fulfillment_worker,
                "interval": 600,  # 10 minutes
                "last_run": None,
                "enabled": True
            },
            "selloship_status": {
                "func": run_selloship_status_worker,
                "interval": 900,  # 15 minutes
                "last_run": None,
                "enabled": True
            }
        }
        self.running = False
    
    async def run_worker(self, worker_name: str, worker_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a single worker and log results.
        
        Args:
            worker_name: Name of the worker
            worker_config: Worker configuration
            
        Returns:
            Worker result
        """
        try:
            logger.info(f"Starting worker: {worker_name}")
            result = await asyncio.get_event_loop().run_in_executor(
                None, worker_config["func"]
            )
            
            worker_config["last_run"] = datetime.now(timezone.utc)
            
            if result.get("success", False):
                logger.info(f"Worker {worker_name} completed: {result.get('message', 'No message')}")
            else:
                logger.error(f"Worker {worker_name} failed: {result.get('message', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Worker {worker_name} crashed: {e}")
            return {
                "success": False,
                "message": f"Worker crashed: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def start_scheduler(self):
        """Start the background worker scheduler."""
        self.running = True
        logger.info("🚀 Worker scheduler started")
        
        while self.running:
            current_time = datetime.now(timezone.utc)
            
            for worker_name, worker_config in self.workers.items():
                if not worker_config["enabled"]:
                    continue
                
                # Check if worker should run
                last_run = worker_config["last_run"]
                interval = worker_config["interval"]
                
                if last_run is None or (current_time - last_run).total_seconds() >= interval:
                    # Run worker asynchronously
                    asyncio.create_task(
                        self.run_worker(worker_name, worker_config)
                    )
            
            # Sleep for 60 seconds before next check
            await asyncio.sleep(60)
    
    def stop_scheduler(self):
        """Stop the background worker scheduler."""
        self.running = False
        logger.info("⏹️ Worker scheduler stopped")
    
    def get_worker_status(self) -> Dict[str, Any]:
        """Get current status of all workers."""
        current_time = datetime.now(timezone.utc)
        status = {}
        
        for worker_name, worker_config in self.workers.items():
            last_run = worker_config["last_run"]
            next_run = None
            
            if last_run:
                next_run = last_run + timedelta(seconds=worker_config["interval"])
            
            status[worker_name] = {
                "enabled": worker_config["enabled"],
                "last_run": last_run.isoformat() if last_run else None,
                "next_run": next_run.isoformat() if next_run else None,
                "interval_seconds": worker_config["interval"],
                "status": "running" if self.running else "stopped"
            }
        
        return status


# Global scheduler instance
scheduler = WorkerScheduler()


def start_background_workers():
    """Start the background worker scheduler."""
    try:
        asyncio.create_task(scheduler.start_scheduler())
        logger.info("✅ Background workers started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start background workers: {e}")


def stop_background_workers():
    """Stop the background worker scheduler."""
    scheduler.stop_scheduler()


def get_workers_status() -> Dict[str, Any]:
    """Get status of all background workers."""
    return scheduler.get_worker_status()


# For manual testing
if __name__ == "__main__":
    async def test_workers():
        print("🧪 Testing workers...")
        
        # Test Shopify fulfillment worker
        print("\n📦 Testing Shopify fulfillment worker...")
        result1 = await scheduler.run_worker("shopify_fulfillment", scheduler.workers["shopify_fulfillment"])
        print(f"Result: {result1}")
        
        # Test Selloship status worker
        print("\n🚚 Testing Selloship status worker...")
        result2 = await scheduler.run_worker("selloship_status", scheduler.workers["selloship_status"])
        print(f"Result: {result2}")
        
        print("\n✅ Worker testing completed")
    
    asyncio.run(test_workers())
