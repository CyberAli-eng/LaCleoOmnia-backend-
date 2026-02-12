"""
Amazon webhook handler for SP-API notifications and marketplace events.
"""
import json
import logging
import hmac
import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models import (
    Channel,
    ChannelAccount,
    ChannelType,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMode,
    FulfillmentStatus,
    WebhookEvent,
)
from app.services.profit_calculator import compute_profit_for_order

logger = logging.getLogger(__name__)

def verify_amazon_webhook(payload: bytes, signature: str, public_key: str) -> bool:
    """
    Verify Amazon webhook signature using RSA-SHA256.
    Amazon uses public key verification for SP-API notifications.
    """
    try:
        import base64
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        
        # Decode the signature
        signature_bytes = base64.b64decode(signature)
        
        # Load the public key
        public_key_obj = load_pem_public_key(public_key.encode(), default_backend())
        
        # Verify the signature
        public_key_obj.verify(
            signature_bytes,
            payload,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        logger.warning("Amazon webhook signature verification failed: %s", e)
        return False

async def process_amazon_webhook(
    db: Session,
    marketplace_id: str,
    notification_type: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
) -> None:
    """
    Process Amazon SP-API notifications.
    Handles: ORDER_CHANGE, FEED_PROCESSING_FINISHED, REPORT_PROCESSING_FINISHED
    """
    try:
        if notification_type == "ORDER_CHANGE":
            await _handle_order_change(db, marketplace_id, payload)
        elif notification_type == "FEED_PROCESSING_FINISHED":
            await _handle_feed_processing(db, marketplace_id, payload)
        elif notification_type == "REPORT_PROCESSING_FINISHED":
            await _handle_report_processing(db, marketplace_id, payload)
        else:
            logger.info("Amazon notification type %s: no handler", notification_type)

        if event_id:
            event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
            if event:
                from datetime import datetime, timezone
                event.processed_at = datetime.now(timezone.utc)
                db.flush()
    except Exception as e:
        logger.exception("Amazon webhook process error: %s", e)
        if event_id:
            event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
            if event:
                event.error = str(e)[:500]
                db.flush()
        raise

async def _handle_order_change(db: Session, marketplace_id: str, payload: Dict[str, Any]) -> None:
    """Handle Amazon order change notifications."""
    try:
        order_info = payload.get("payload", {}).get("OrderChangeNotification", {})
        amazon_order_id = order_info.get("AmazonOrderId")
        
        if not amazon_order_id:
            logger.warning("Amazon order change notification missing AmazonOrderId")
            return

        # Find the channel account for this marketplace
        channel = db.query(Channel).filter(Channel.name == ChannelType.AMAZON).first()
        if not channel:
            logger.error("Amazon channel not found")
            return

        account = db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == channel.id,
            ChannelAccount.marketplace_id == marketplace_id
        ).first()

        if not account:
            logger.warning("No Amazon channel account found for marketplace %s", marketplace_id)
            return

        # Check if order exists
        existing_order = db.query(Order).filter(
            Order.channel_order_id == amazon_order_id,
            Order.channel_id == channel.id
        ).first()

        # Process order update (you would need to implement Amazon API call to get full order details)
        # For now, just log the notification
        logger.info("Received Amazon order change for order %s", amazon_order_id)
        
        if existing_order:
            # Update order status based on notification
            # This would need mapping from Amazon statuses to your OrderStatus enum
            pass

    except Exception as e:
        logger.error("Error handling Amazon order change: %s", e)
        raise

async def _handle_feed_processing(db: Session, marketplace_id: str, payload: Dict[str, Any]) -> None:
    """Handle Amazon feed processing notifications."""
    feed_info = payload.get("payload", {}).get("FeedProcessingNotification", {})
    feed_id = feed_info.get("feedId")
    result = feed_info.get("resultProcessingStatus")
    
    logger.info("Amazon feed %s processed with status: %s", feed_id, result)

async def _handle_report_processing(db: Session, marketplace_id: str, payload: Dict[str, Any]) -> None:
    """Handle Amazon report processing notifications."""
    report_info = payload.get("payload", {}).get("ReportProcessingNotification", {})
    report_id = report_info.get("reportId")
    result = report_info.get("resultProcessingStatus")
    
    logger.info("Amazon report %s processed with status: %s", report_id, result)
