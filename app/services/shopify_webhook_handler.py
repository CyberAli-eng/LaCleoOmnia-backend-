"""
Shopify webhook: HMAC verification and event processing.
Persist event, then trigger sync/profit by topic.
"""
import base64
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Channel,
    ChannelAccount,
    ChannelType,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMode,
    FulfillmentStatus,
    ShopifyIntegration,
    WebhookEvent,
)
from app.services.shopify_inventory_persist import persist_shopify_inventory
from app.services.shopify_service import get_inventory as shopify_get_inventory
from app.services.profit_calculator import compute_profit_for_order

logger = logging.getLogger(__name__)


def verify_webhook_hmac(body: bytes, hmac_header: Optional[str], secret: Optional[str]) -> bool:
    """
    Verify X-Shopify-Hmac-Sha256: HMAC-SHA256(raw_body, secret) base64 == header.
    """
    if not secret or not hmac_header or not body:
        return False
    try:
        computed = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        computed_b64 = base64.b64encode(computed).decode("utf-8")
        return hmac.compare_digest(computed_b64, hmac_header.strip())
    except Exception as e:
        logger.warning("Webhook HMAC verify error: %s", e)
        return False


def _format_address(addr: Optional[dict]) -> Optional[str]:
    if not addr or not isinstance(addr, dict):
        return None
    parts = []
    if (addr.get("address1") or "").strip():
        parts.append((addr.get("address1") or "").strip())
    if (addr.get("address2") or "").strip():
        parts.append((addr.get("address2") or "").strip())
    city = (addr.get("city") or "").strip()
    prov = (addr.get("province_code") or addr.get("province") or "").strip()
    zip_ = (addr.get("zip") or "").strip()
    country = (addr.get("country") or "").strip()
    if city or prov or zip_ or country:
        parts.append(", ".join(p for p in [city, prov, zip_, country] if p))
    line = ", ".join(parts)
    return line[:1024] if line else None


def _get_integration_and_account(db: Session, shop_domain: str):
    """Return (ShopifyIntegration, ChannelAccount) for shop. ChannelAccount may be None if no user linked yet."""
    integration = db.query(ShopifyIntegration).filter(ShopifyIntegration.shop_domain == shop_domain).first()
    if not integration:
        return None, None
    channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
    if not channel:
        return integration, None
    account = (
        db.query(ChannelAccount)
        .filter(ChannelAccount.channel_id == channel.id, ChannelAccount.shop_domain == shop_domain)
        .first()
    )
    return integration, account


def _upsert_order_from_payload(db: Session, shop_domain: str, payload: dict) -> Optional[str]:
    """
    Upsert order from Shopify webhook payload (full order object). Returns order.id or None.
    """
    integration, account = _get_integration_and_account(db, shop_domain)
    if not integration or not account:
        logger.warning("Webhook: no integration or account for shop %s", shop_domain)
        return None
    channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
    if not channel:
        return None

    shopify_id = str(payload.get("id") or "")
    if not shopify_id:
        return None

    existing = (
        db.query(Order)
        .filter(Order.channel_id == channel.id, Order.channel_order_id == shopify_id)
        .first()
    )

    billing = payload.get("billing_address") or {}
    first = (billing.get("first_name") or "").strip()
    last = (billing.get("last_name") or "").strip()
    customer_name = f"{first} {last}".strip() if (first or last) else (payload.get("email") or "Customer")[:100]
    customer_email = (payload.get("email") or "").strip() or None
    total = float(payload.get("total_price", 0) or 0)
    financial = (payload.get("financial_status") or "").lower()
    payment_mode = PaymentMode.PREPAID if financial == "paid" else PaymentMode.COD
    shipping_addr = _format_address(payload.get("shipping_address"))
    billing_addr = _format_address(payload.get("billing_address"))

    if existing:
        existing.customer_name = customer_name[:255]
        existing.customer_email = customer_email[:255] if customer_email else None
        existing.order_total = Decimal(str(total))
        existing.payment_mode = payment_mode
        existing.shipping_address = shipping_addr
        existing.billing_address = billing_addr
        # Do not overwrite status with NEW on update; keep existing workflow state unless cancelled
        order_id = existing.id
        db.query(OrderItem).filter(OrderItem.order_id == existing.id).delete()
        db.flush()
    else:
        order = Order(
            channel_id=channel.id,
            channel_account_id=account.id,
            channel_order_id=shopify_id,
            customer_name=customer_name[:255],
            customer_email=customer_email[:255] if customer_email else None,
            shipping_address=shipping_addr,
            billing_address=billing_addr,
            payment_mode=payment_mode,
            order_total=Decimal(str(total)),
            status=OrderStatus.NEW,
        )
        db.add(order)
        db.flush()
        order_id = order.id

    for line in payload.get("line_items") or []:
        sku = (line.get("sku") or str(line.get("variant_id") or "") or "—")[:64]
        title = (line.get("title") or "Item")[:255]
        qty = int(line.get("quantity", 0) or 0)
        price = float(line.get("price", 0) or 0)
        db.add(
            OrderItem(
                order_id=order_id,
                sku=sku,
                title=title,
                qty=qty,
                price=Decimal(str(price)),
                fulfillment_status=FulfillmentStatus.PENDING,
            )
        )
    db.flush()
    return order_id


def process_shopify_webhook(
    db: Session,
    shop_domain: str,
    topic: str,
    payload: dict,
    event_id: Optional[str] = None,
) -> None:
    """
    Dispatch by topic: upsert order, cancel order, recompute profit, or sync inventory.
    """
    try:
        if topic in ("orders/create", "orders/updated"):
            order_id = _upsert_order_from_payload(db, shop_domain, payload)
            if order_id:
                compute_profit_for_order(db, order_id)
                logger.info("Webhook %s: upserted order %s and recomputed profit", topic, order_id)
        elif topic == "orders/cancelled":
            shopify_id = str(payload.get("id") or "")
            if shopify_id:
                channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
                if channel:
                    order = (
                        db.query(Order)
                        .filter(Order.channel_id == channel.id, Order.channel_order_id == shopify_id)
                        .first()
                    )
                    if order:
                        order.status = OrderStatus.CANCELLED
                        db.flush()
                        compute_profit_for_order(db, order.id)
                        logger.info("Webhook orders/cancelled: cancelled order %s", order.id)
        elif topic == "refunds/create":
            order_id_shopify = payload.get("order_id")
            if order_id_shopify:
                channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
                if channel:
                    order = (
                        db.query(Order)
                        .filter(
                            Order.channel_id == channel.id,
                            Order.channel_order_id == str(order_id_shopify),
                        )
                        .first()
                    )
                    if order:
                        compute_profit_for_order(db, order.id)
                        logger.info("Webhook refunds/create: recomputed profit for order %s", order.id)
        elif topic in ("inventory_levels/update", "products/update"):
            integration, _ = _get_integration_and_account(db, shop_domain)
            if integration:
                try:
                    inv_list = shopify_get_inventory(integration.shop_domain, integration.access_token)
                    persist_shopify_inventory(db, integration.shop_domain, inv_list or [])
                    logger.info("Webhook %s: synced inventory for %s", topic, shop_domain)
                except Exception as e:
                    logger.warning("Webhook inventory sync failed: %s", e)
        else:
            logger.debug("Webhook topic %s: no handler", topic)

        if event_id:
            event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
            if event:
                event.processed_at = datetime.now(timezone.utc)
                db.flush()
    except Exception as e:
        logger.exception("Webhook process error: %s", e)
        if event_id:
            event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
            if event:
                event.error = str(e)[:500]
                db.flush()
        raise
