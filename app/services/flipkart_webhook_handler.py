"""
Flipkart webhook handler for marketplace notifications.
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

def verify_flipkart_webhook(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify Flipkart webhook signature using HMAC-SHA256.
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
        logger.warning("Flipkart webhook signature verification failed: %s", e)
        return False

async def process_flipkart_webhook(
    db: Session,
    seller_id: str,
    event_type: str,
    payload: Dict[str, Any],
    event_id: Optional[str] = None,
) -> None:
    """
    Process Flipkart webhook notifications.
    Handles: ORDER_CREATED, ORDER_UPDATED, SHIPMENT_CREATED, PAYMENT_UPDATED
    """
    try:
        if event_type == "ORDER_CREATED":
            await _handle_order_created(db, seller_id, payload)
        elif event_type == "ORDER_UPDATED":
            await _handle_order_updated(db, seller_id, payload)
        elif event_type == "SHIPMENT_CREATED":
            await _handle_shipment_created(db, seller_id, payload)
        elif event_type == "PAYMENT_UPDATED":
            await _handle_payment_updated(db, seller_id, payload)
        else:
            logger.info("Flipkart event type %s: no handler", event_type)

        if event_id:
            event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
            if event:
                from datetime import datetime, timezone
                event.processed_at = datetime.now(timezone.utc)
                db.flush()
    except Exception as e:
        logger.exception("Flipkart webhook process error: %s", e)
        if event_id:
            event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
            if event:
                event.error = str(e)[:500]
                db.flush()
        raise

async def _handle_order_created(db: Session, seller_id: str, payload: Dict[str, Any]) -> None:
    """Handle Flipkart order creation."""
    try:
        order_data = payload.get("order", {})
        flipkart_order_id = order_data.get("orderId")
        
        if not flipkart_order_id:
            logger.warning("Flipkart order creation notification missing orderId")
            return

        # Find the channel account for this seller
        channel = db.query(Channel).filter(Channel.name == ChannelType.FLIPKART).first()
        if not channel:
            logger.error("Flipkart channel not found")
            return

        account = db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == channel.id,
            ChannelAccount.seller_id == seller_id
        ).first()

        if not account:
            logger.warning("No Flipkart channel account found for seller %s", seller_id)
            return

        # Check if order already exists
        existing_order = db.query(Order).filter(
            Order.channel_order_id == flipkart_order_id,
            Order.channel_id == channel.id
        ).first()

        if existing_order:
            logger.info("Flipkart order %s already exists", flipkart_order_id)
            return

        # Create new order (simplified - you'd need to map Flipkart fields)
        customer_info = order_data.get("customer", {})
        total_amount = order_data.get("totalAmount", 0)
        
        new_order = Order(
            channel_id=channel.id,
            channel_account_id=account.id,
            channel_order_id=flipkart_order_id,
            customer_name=customer_info.get("name", "Flipkart Customer")[:255],
            customer_email=customer_info.get("email", "")[:255] or None,
            order_total=float(total_amount),
            payment_mode=PaymentMode.PREPAID if order_data.get("paymentMode") == "PREPAID" else PaymentMode.COD,
            status=OrderStatus.NEW,
        )
        
        db.add(new_order)
        db.flush()
        
        # Process order items
        for item in order_data.get("orderItems", []):
            order_item = OrderItem(
                order_id=new_order.id,
                sku=item.get("sku", "")[:64],
                title=item.get("title", "Item")[:255],
                qty=int(item.get("quantity", 0)),
                price=float(item.get("price", 0)),
                fulfillment_status=FulfillmentStatus.PENDING,
            )
            db.add(order_item)

        # Compute profit
        compute_profit_for_order(db, new_order.id)
        logger.info("Created Flipkart order %s from webhook", flipkart_order_id)

    except Exception as e:
        logger.error("Error handling Flipkart order creation: %s", e)
        raise

async def _handle_order_updated(db: Session, seller_id: str, payload: Dict[str, Any]) -> None:
    """Handle Flipkart order updates."""
    order_data = payload.get("order", {})
    flipkart_order_id = order_data.get("orderId")
    
    if not flipkart_order_id:
        return

    channel = db.query(Channel).filter(Channel.name == ChannelType.FLIPKART).first()
    if not channel:
        return

    order = db.query(Order).filter(
        Order.channel_order_id == flipkart_order_id,
        Order.channel_id == channel.id
    ).first()

    if order:
        # Update order status based on Flipkart status
        # Map Flipkart statuses to your OrderStatus enum
        flipkart_status = order_data.get("status")
        if flipkart_status:
            # Add status mapping logic here
            pass
        
        compute_profit_for_order(db, order.id)
        logger.info("Updated Flipkart order %s from webhook", flipkart_order_id)

async def _handle_shipment_created(db: Session, seller_id: str, payload: Dict[str, Any]) -> None:
    """Handle Flipkart shipment creation."""
    shipment_data = payload.get("shipment", {})
    logger.info("Flipkart shipment created: %s", shipment_data.get("shipmentId"))

async def _handle_payment_updated(db: Session, seller_id: str, payload: Dict[str, Any]) -> None:
    """Handle Flipkart payment updates."""
    payment_data = payload.get("payment", {})
    logger.info("Flipkart payment updated: %s", payment_data.get("paymentId"))
