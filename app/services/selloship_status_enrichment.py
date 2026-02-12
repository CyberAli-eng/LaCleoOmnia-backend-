"""
Selloship Status Enrichment Service
Focused solely on status enrichment for existing tracking numbers
No AWB discovery or order creation - only status updates
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models import OrderShipment, ShipmentStatus
from app.services.selloship_service import get_selloship_client, map_selloship_status

logger = logging.getLogger(__name__)


class SelloshipStatusEnrichment:
    """Selloship status enrichment service for Shopify-centric tracking"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def enrich_shipment_status(self, tracking_number: str, user_id: str) -> Dict:
        """
        Enrich status for a single tracking number using user-specific credentials
        """
        if not tracking_number:
            return {"status": "FAILED", "error": "No tracking number provided"}
        
        from app.services.selloship_service import get_user_selloship_client
        client = get_user_selloship_client(self.db, user_id)
        if not client:
            return {"status": "FAILED", "error": f"Selloship not configured for user {user_id}"}
        
        try:
            # Get tracking info from Selloship
            result = await client.get_tracking(tracking_number)
            
            if result.get("error"):
                logger.warning(f"Selloship error for {tracking_number}: {result.get('error')}")
                return {"status": "FAILED", "error": result.get("error")}
            
            # Map Selloship status to internal status
            selloship_status = result.get("raw_status")
            internal_status = map_selloship_status(selloship_status)
            
            # Update order_shipment record
            shipment = self.db.query(OrderShipment).filter(
                OrderShipment.tracking_number == tracking_number
            ).first()
            
            if shipment:
                shipment.selloship_status = selloship_status
                shipment.last_synced_at = datetime.now(timezone.utc)
                
                # If Selloship provides more detailed delivery status, update it
                if result.get("delivery_status"):
                    shipment.delivery_status = result.get("delivery_status")
                
                self.db.commit()
                
                return {
                    "status": "SUCCESS",
                    "tracking_number": tracking_number,
                    "selloship_status": selloship_status,
                    "internal_status": internal_status.value,
                    "delivery_status": shipment.delivery_status,
                    "current_location": result.get("current_location"),
                    "status_date": result.get("status_date")
                }
            else:
                return {"status": "FAILED", "error": f"Shipment with tracking {tracking_number} not found"}
        
        except Exception as e:
            logger.error(f"Failed to enrich status for {tracking_number}: {e}")
            return {"status": "FAILED", "error": str(e)}
    
    async def enrich_batch_status(self, tracking_numbers: List[str], user_id: str) -> Dict:
        """
        Enrich status for multiple tracking numbers using user-specific credentials
        """
        if not tracking_numbers:
            return {"status": "SUCCESS", "message": "No tracking numbers provided", "stats": {"processed": 0, "updated": 0, "errors": 0}}
        
        from app.services.selloship_service import get_user_selloship_client
        client = get_user_selloship_client(self.db, user_id)
        if not client:
            return {"status": "FAILED", "error": f"Selloship not configured for user {user_id}"}
        
        stats = {"processed": 0, "updated": 0, "errors": 0}
        errors = []
        
        # Process in batches of 50 (Selloship API limit)
        batch_size = 50
        for i in range(0, len(tracking_numbers), batch_size):
            batch = tracking_numbers[i:i + batch_size]
            
            try:
                # Get batch tracking info
                results = await client.get_waybill_details_batch(batch)
                
                for result in results:
                    tracking_number = result.get("waybill")
                    if not tracking_number:
                        continue
                    
                    stats["processed"] += 1
                    
                    if result.get("error"):
                        stats["errors"] += 1
                        errors.append(f"{tracking_number}: {result.get('error')}")
                        continue
                    
                    # Update shipment record
                    shipment = self.db.query(OrderShipment).filter(
                        OrderShipment.tracking_number == tracking_number
                    ).first()
                    
                    if shipment:
                        selloship_status = result.get("raw_status")
                        
                        shipment.selloship_status = selloship_status
                        shipment.last_synced_at = datetime.now(timezone.utc)
                        
                        # Update delivery status if provided
                        if result.get("delivery_status"):
                            shipment.delivery_status = result.get("delivery_status")
                        
                        stats["updated"] += 1
                        logger.info(f"Updated status for {tracking_number}: {selloship_status}")
                    else:
                        stats["errors"] += 1
                        errors.append(f"{tracking_number}: Shipment not found")
                
                # Commit batch changes
                try:
                    self.db.commit()
                except Exception as e:
                    self.db.rollback()
                    logger.error(f"Failed to commit batch changes: {e}")
                    stats["errors"] += len(batch)
                    errors.append(f"Batch commit failed: {e}")
                
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
                stats["errors"] += len(batch)
                errors.append(f"Batch error: {e}")
        
        return {
            "status": "SUCCESS" if stats["errors"] == 0 else "PARTIAL",
            "message": f"Processed {stats['processed']} tracking numbers, updated {stats['updated']}, {stats['errors']} errors",
            "stats": stats,
            "errors": errors
        }
    
    async def enrich_all_active_shipments(self, limit: int = 100) -> Dict:
        """
        Enrich status for all active shipments (excluding final statuses)
        Groups shipments by user_id to use user-specific credentials
        """
        # Get shipments that need status enrichment
        final_statuses = ['DELIVERED', 'RTO', 'LOST', 'CANCELLED']
        
        shipments = self.db.query(OrderShipment).filter(
            OrderShipment.tracking_number.isnot(None),
            ~OrderShipment.delivery_status.in_(final_statuses)
        ).limit(limit).all()
        
        if not shipments:
            return {"status": "SUCCESS", "message": "No active shipments found", "stats": {"processed": 0, "updated": 0, "errors": 0}}
        
        # Group shipments by user_id for user-specific credential access
        from collections import defaultdict
        user_shipments = defaultdict(list)
        for shipment in shipments:
            user_shipments[shipment.order_id].append(shipment)
        
        # Process each user's shipments separately
        total_stats = {"processed": 0, "updated": 0, "errors": 0}
        
        for user_id, user_specific_shipments in user_shipments.items():
            tracking_numbers = [s.tracking_number for s in user_specific_shipments if s.tracking_number]
            if not tracking_numbers:
                continue
                
            result = await self.enrich_batch_status(tracking_numbers, user_id)
            
            # Aggregate stats
            if result.get("status") == "SUCCESS":
                stats = result.get("stats", {})
                total_stats["processed"] += stats.get("processed", 0)
                total_stats["updated"] += stats.get("updated", 0)
                total_stats["errors"] += stats.get("errors", 0)
            else:
                total_stats["errors"] += 1
        
        return {
            "status": "SUCCESS", 
            "message": f"Processed {len(user_shipments)} users with {total_stats['processed']} shipments",
            "stats": total_stats
        }
    
    async def enrich_shipment_by_order_id(self, order_id: str) -> Dict:
        """
        Enrich status for all shipments belonging to an order
        """
        shipments = self.db.query(OrderShipment).filter(
            OrderShipment.order_id == order_id,
            OrderShipment.tracking_number.isnot(None)
        ).all()
        
        if not shipments:
            return {"status": "FAILED", "error": f"No shipments found for order {order_id}"}
        
        tracking_numbers = [s.tracking_number for s in shipments]
        return await self.enrich_batch_status(tracking_numbers)


# Convenience functions for easy usage
async def enrich_shipment_status(db: Session, tracking_number: str) -> Dict:
    """Convenience function to enrich status for a single tracking number"""
    enrichment_service = SelloshipStatusEnrichment(db)
    return await enrichment_service.enrich_shipment_status(tracking_number)


async def enrich_all_active_shipments(db: Session, limit: int = 100) -> Dict:
    """Convenience function to enrich status for all active shipments"""
    enrichment_service = SelloshipStatusEnrichment(db)
    return await enrichment_service.enrich_all_active_shipments(limit)


async def enrich_shipment_status_by_order(db: Session, order_id: str) -> Dict:
    """Convenience function to enrich status for shipments by order ID"""
    enrichment_service = SelloshipStatusEnrichment(db)
    return await enrichment_service.enrich_shipment_by_order_id(order_id)
