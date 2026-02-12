"""
Selloship webhook handler for shipment status updates.
"""
import json
import logging
import hmac
import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models import (
    Order,
    ShipmentStatus,
)
from app.services.realtime_service import realtime_service

logger = logging.getLogger(__name__)

def verify_selloship_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Selloship webhook signature using HMAC-SHA256.
    """
    if not secret or not signature or not payload:
        return False
    try:
        import base64
        computed = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()
        computed_b64 = base64.b64encode(computed).decode("utf-8")
        return hmac.compare_digest(computed_b64, signature.strip())
    except Exception as e:
        logger.warning("Selloship webhook signature verification failed: %s", e)
        return False

async def process_selloship_webhook(
    db: Session,
    tracking_number: str,
    event_type: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
) -> None:
    """
    Process Selloship webhook notifications.
    Handles: SHIPMENT_CREATED, SHIPMENT_UPDATED, SHIPMENT_DELIVERED, SHIPMENT_RTO
    """
    try:
        if event_type in ("SHIPMENT_UPDATED", "SHIPMENT_DELIVERED", "SHIPMENT_RTO"):
            await _handle_shipment_update(db, tracking_number, event_type, payload)
        elif event_type == "SHIPMENT_CREATED":
            await _handle_shipment_created(db, tracking_number, payload)
        else:
            logger.info("Selloship event type %s: no handler", event_type)

        # Broadcast real-time update
        await realtime_service.broadcast_order_update(
            db, tracking_number, f"selloship_{event_type.lower()}"
        )
        
    except Exception as e:
        logger.exception("Selloship webhook process error: %s", e)
        raise

async def _handle_shipment_update(db: Session, tracking_number: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Handle shipment status updates from Selloship"""
    try:
        # Find order by tracking number
        order = db.query(Order).filter(
            Order.shipments.any(tracking_number=tracking_number)
        ).first()
        
        if not order:
            logger.warning("No order found for tracking number: %s", tracking_number)
            return

        # Map Selloship status to our ShipmentStatus enum
        status_mapping = {
            "IN_TRANSIT": ShipmentStatus.IN_TRANSIT,
            "DELIVERED": ShipmentStatus.DELIVERED,
            "RTO_INITIATED": ShipmentStatus.RTO_INITIATED,
            "RTO_DONE": ShipmentStatus.RTO_DONE,
            "LOST": ShipmentStatus.LOST,
        }
        
        selloship_status = payload.get("status")
        if selloship_status and selloship_status in status_mapping:
            # Update shipment status in order
            for shipment in order.shipments or []:
                if shipment.tracking_number == tracking_number:
                    shipment.delivery_status = selloship_status
                    shipment.selloship_status = selloship_status
                    break
            
            # Update order status based on shipment
            if selloship_status == "DELIVERED":
                order.status = "DELIVERED"
            elif selloship_status in ["RTO_INITIATED", "RTO_DONE"]:
                order.status = "RETURNED"
            
            db.flush()
            logger.info("Updated shipment %s status to %s", tracking_number, selloship_status)
        
    except Exception as e:
        logger.error("Error handling shipment update: %s", e)
        raise

async def _handle_shipment_created(db: Session, tracking_number: str, payload: Dict[str, Any]) -> None:
    """Handle new shipment creation from Selloship"""
    try:
        order = db.query(Order).filter(
            Order.shipments.any(tracking_number=tracking_number)
        ).first()
        
        if not order:
            logger.warning("No order found for tracking number: %s", tracking_number)
            return
        
        logger.info("Sellohip shipment created for tracking: %s", tracking_number)
        
    except Exception as e:
        logger.error("Error handling shipment creation: %s", e)
        raise
