"""
Selloship Status Enrichment Worker

Enriches shipment data with Selloship tracking status.
Only runs for shipments that have tracking numbers but no Selloship status yet.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.database import get_db
from app.models import OrderShipment
from app.services.selloship_service import SelloshipService

logger = logging.getLogger(__name__)


class SelloshipStatusWorker:
    """Worker for enriching shipment status with Selloship tracking data."""
    
    def __init__(self):
        self.name = "selloship_status_worker"
        self.interval = 900  # 15 minutes in seconds
        self.batch_size = 50  # Process 50 shipments at a time
    
    def get_shipments_needing_enrichment(self, db: Session) -> List[OrderShipment]:
        """
        Get shipments that need Selloship status enrichment.
        
        Args:
            db: Database session
            
        Returns:
            List of OrderShipment objects needing enrichment
        """
        try:
            # Get shipments with tracking numbers but no Selloship status
            # or with stale Selloship status (older than 24 hours)
            stale_threshold = datetime.now(timezone.utc) - timedelta(hours=24)
            
            shipments = db.query(OrderShipment).filter(
                and_(
                    OrderShipment.tracking_number.isnot(None),
                    OrderShipment.tracking_number != "",
                    or_(
                        OrderShipment.selloship_status.is_(None),
                        OrderShipment.last_synced_at < stale_threshold
                    )
                )
            ).order_by(OrderShipment.created_at.desc()).limit(self.batch_size).all()
            
            logger.info(f"Found {len(shipments)} shipments needing Selloship enrichment")
            return shipments
            
        except Exception as e:
            logger.error(f"Failed to get shipments needing enrichment: {e}")
            return []
    
    def enrich_shipment_with_selloship(self, shipment: OrderShipment, selloship_service: SelloshipService) -> bool:
        """
        Enrich a single shipment with Selloship status.
        
        Args:
            shipment: OrderShipment object to enrich
            selloship_service: SelloshipService instance
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get waybill details from Selloship
            waybill_data = selloship_service.get_waybill_details(shipment.tracking_number)
            
            if not waybill_data:
                logger.warning(f"No waybill data found for tracking {shipment.tracking_number}")
                return False
            
            # Extract status information
            current_status = waybill_data.get("status", "").upper()
            delivery_status = waybill_data.get("delivery_status", "")
            
            # Map Selloship status to our internal status
            status_mapping = {
                "IN_TRANSIT": "IN_TRANSIT",
                "DISPATCHED": "IN_TRANSIT", 
                "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
                "DELIVERED": "DELIVERED",
                "RTO": "RTO",
                "LOST": "LOST",
                "CANCELLED": "CANCELLED",
                "PENDING": "PENDING"
            }
            
            mapped_status = status_mapping.get(current_status, current_status)
            
            # Update shipment with Selloship data
            shipment.selloship_status = current_status
            shipment.delivery_status = delivery_status or mapped_status
            shipment.last_synced_at = datetime.now(timezone.utc)
            
            logger.info(f"Updated shipment {shipment.id} with Selloship status: {current_status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enrich shipment {shipment.id}: {e}")
            return False
    
    def run_enrichment_cycle(self) -> Dict[str, Any]:
        """
        Run a single enrichment cycle for all shipments needing updates.
        
        Returns:
            Summary of enrichment results
        """
        try:
            db = next(get_db())
            
            # Get shipments needing enrichment
            shipments = self.get_shipments_needing_enrichment(db)
            
            if not shipments:
                db.close()
                return {
                    "success": True,
                    "message": "No shipments need enrichment",
                    "total_processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            # Initialize Selloship service
            selloship_service = SelloshipService()
            
            successful = 0
            failed = 0
            
            logger.info(f"Starting enrichment for {len(shipments)} shipments")
            
            for shipment in shipments:
                try:
                    if self.enrich_shipment_with_selloship(shipment, selloship_service):
                        successful += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to process shipment {shipment.id}: {e}")
            
            # Commit all changes
            try:
                db.commit()
                logger.info(f"Committed {successful} successful, {failed} failed enrichment updates")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to commit enrichment changes: {e}")
                return {
                    "success": False,
                    "message": f"Commit failed: {str(e)}",
                    "total_processed": len(shipments),
                    "successful": 0,
                    "failed": len(shipments),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            db.close()
            
            return {
                "success": True,
                "message": f"Processed {len(shipments)} shipments: {successful} successful, {failed} failed",
                "total_processed": len(shipments),
                "successful": successful,
                "failed": failed,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Selloship enrichment cycle failed: {e}")
            return {
                "success": False,
                "message": f"Enrichment cycle failed: {str(e)}",
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def run_single_enrichment(self) -> Dict[str, Any]:
        """
        Run a single enrichment cycle (called by scheduler).
        
        Returns:
            Enrichment result
        """
        logger.info("Starting Selloship status enrichment cycle")
        result = self.run_enrichment_cycle()
        
        if result["success"]:
            logger.info(f"Selloship enrichment completed: {result['message']}")
        else:
            logger.error(f"Selloship enrichment failed: {result['message']}")
        
        return result


def run_selloship_status_worker() -> Dict[str, Any]:
    """
    Entry point for the Selloship status worker.
    
    Returns:
        Enrichment result
    """
    worker = SelloshipStatusWorker()
    return worker.run_single_enrichment()


if __name__ == "__main__":
    # For testing purposes
    result = run_selloship_status_worker()
    print(f"Selloship worker result: {result}")
