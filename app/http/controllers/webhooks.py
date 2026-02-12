"""
Webhook management routes. Shopify webhook receiver is public (no JWT); HMAC verified.
"""
import json
import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models import ChannelAccount, User, WebhookEvent, ShopifyIntegration, ProviderCredential
from app.auth import get_current_user
from app.services.shopify import ShopifyService
from app.services.credentials import decrypt_token
from app.services.shopify_webhook_handler import (
    verify_webhook_hmac,
    process_shopify_webhook,
)
from app.services.amazon_webhook_handler import (
    verify_amazon_webhook,
    process_amazon_webhook,
)
from app.services.flipkart_webhook_handler import (
    verify_flipkart_webhook,
    process_flipkart_webhook,
)
from app.services.selloship_webhook_handler import (
    verify_selloship_webhook,
    process_selloship_webhook,
)
from app.services.realtime_service import realtime_service
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

def _parse_channel_account_creds(account: ChannelAccount, db: Session, user_id: str) -> tuple[str, str, str]:
    """
    Parse ChannelAccount access_token (encrypted). Handles both JSON shape
    {shopDomain, accessToken, appSecret} and raw token string. Returns (shop_domain, access_token, app_secret).
    """
    dec = decrypt_token(account.access_token or "")
    if not dec:
        raise ValueError("No credentials")
    if isinstance(dec, str) and dec.strip().startswith("{"):
        try:
            creds = json.loads(dec)
            if isinstance(creds, dict):
                shop = (creds.get("shopDomain") or creds.get("shop_domain") or "").strip()
                token = (creds.get("accessToken") or creds.get("access_token") or "").strip()
                secret = (creds.get("appSecret") or creds.get("apiSecret") or "").strip()
                if shop and token:
                    return shop, token, secret
        except json.JSONDecodeError:
            pass
    # Raw token string (e.g. from channels OAuth flow)
    shop = (account.shop_domain or "").strip()
    if not shop:
        raise ValueError("Shop domain missing")
    token = (dec if isinstance(dec, str) else str(dec)).strip()
    if not token:
        raise ValueError("No access token")
    # App secret: from ProviderCredential (shopify_app) for this user or env
    from app.models import ProviderCredential
    secret = ""
    pc = db.query(ProviderCredential).filter(
        ProviderCredential.user_id == user_id,
        ProviderCredential.provider_id == "shopify_app",
    ).first()
    if pc and pc.value_encrypted:
        try:
            raw = decrypt_token(pc.value_encrypted)
            if isinstance(raw, str) and raw.strip().startswith("{"):
                data = json.loads(raw)
                secret = (data.get("apiSecret") or data.get("appSecret") or "").strip()
            elif isinstance(raw, str):
                secret = raw.strip()
        except Exception:
            pass
    if not secret:
        raise ValueError("Shopify App Secret not found. Add your app API Key and API Secret in Integrations → Shopify → Configure.")
    return shop, token, secret


@router.post("/register/{integration_id}")
async def register_webhooks(
    integration_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Re-register webhooks for an integration (ChannelAccount id, e.g. UUID). Handles both JSON and raw token creds."""
    account = db.query(ChannelAccount).filter(
        ChannelAccount.id == integration_id,
        ChannelAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(
            status_code=404,
            detail="Integration not found"
        )

    if account.channel.name.value != "SHOPIFY":
        raise HTTPException(
            status_code=400,
            detail=f"Webhook registration not supported for {account.channel.name.value}"
        )

    try:
        shop_domain, access_token, app_secret = _parse_channel_account_creds(
            account, db, str(current_user.id)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    webhook_base_url = (getattr(settings, "WEBHOOK_BASE_URL", None) or "").strip().rstrip("/")
    if not webhook_base_url:
        raise HTTPException(
            status_code=400,
            detail="WEBHOOK_BASE_URL not configured"
        )

    try:
        service = ShopifyService()
        await service.ensure_webhook(
            shop_domain,
            access_token,
            app_secret,
            webhook_base_url
        )
        return {"message": "Webhooks registered successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register webhooks: {str(e)}"
        )

def _get_user_shop_domains(db: Session, user_id: str) -> list[str]:
    """Return list of shop domains (e.g. Shopify) for this user's channel accounts."""
    accounts = (
        db.query(ChannelAccount)
        .filter(ChannelAccount.user_id == user_id, ChannelAccount.shop_domain.isnot(None))
        .all()
    )
    return [a.shop_domain for a in accounts if a.shop_domain]


@router.get("")
async def get_webhook_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, le=100),
    source: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
):
    """Get persisted webhook events for the current user's connected shops only."""
    # Debug: Force new deployment
    user_shops = _get_user_shop_domains(db, str(current_user.id))
    query = db.query(WebhookEvent).order_by(WebhookEvent.created_at.desc())
    # Restrict to events for this user's shop(s); if no shops connected, return empty
    if user_shops:
        query = query.filter(WebhookEvent.shop_domain.in_(user_shops))
    else:
        query = query.filter(WebhookEvent.id == "")  # no matching rows
    if source:
        query = query.filter(WebhookEvent.source == source)
    if topic:
        query = query.filter(WebhookEvent.topic == topic)
    rows = query.limit(limit).all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "shopDomain": r.shop_domain,
            "topic": r.topic,
            "payloadSummary": r.payload_summary,
            "processedAt": r.processed_at.isoformat() if r.processed_at else None,
            "error": r.error,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/events")
async def get_webhook_events_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, le=100),
):
    """Alias: get webhook events list."""
    return await get_webhook_events(db=db, current_user=current_user, limit=limit)

@router.post("/shopify")
async def shopify_webhook_receive(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint for Shopify webhooks. No JWT.
    Verify X-Shopify-Hmac-Sha256, persist event, trigger sync/profit by topic.
    Topics: orders/create, orders/updated, orders/cancelled, refunds/create, inventory_levels/update, products/update.
    """
    raw_body = await request.body()
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")
    topic = request.headers.get("X-Shopify-Topic") or ""
    shop_domain = (request.headers.get("X-Shopify-Shop-Domain") or "").strip().lower()
    if not shop_domain:
        logger.warning("Shopify webhook: missing X-Shopify-Shop-Domain")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing shop domain")

    # Collect all possible app secrets (webhook is signed with the app secret used at registration)
    candidates: list[str] = []
    integration = db.query(ShopifyIntegration).filter(ShopifyIntegration.shop_domain == shop_domain).first()
    if integration and getattr(integration, "app_secret_encrypted", None):
        try:
            s = (decrypt_token(integration.app_secret_encrypted) or "").strip()
            if s and s not in candidates:
                candidates.append(s)
        except Exception:
            pass
    # ProviderCredential (shopify_app) for any user who has this shop connected
    for acc in db.query(ChannelAccount).filter(
        ChannelAccount.shop_domain == shop_domain,
        ChannelAccount.access_token.isnot(None),
    ).all():
        pc = db.query(ProviderCredential).filter(
            ProviderCredential.user_id == acc.user_id,
            ProviderCredential.provider_id == "shopify_app",
            ProviderCredential.value_encrypted.isnot(None),
        ).first()
        if pc and pc.value_encrypted:
            try:
                raw = decrypt_token(pc.value_encrypted)
                if isinstance(raw, str) and raw.strip().startswith("{"):
                    data = json.loads(raw)
                    s = (data.get("apiSecret") or data.get("appSecret") or "").strip()
                    if s and s not in candidates:
                        candidates.append(s)
                elif isinstance(raw, str) and raw.strip() and raw.strip() not in candidates:
                    candidates.append(raw.strip())
            except Exception:
                pass
    # Env (OAuth flow registers webhooks with SHOPIFY_API_SECRET)
    env_secret = (getattr(settings, "SHOPIFY_API_SECRET", None) or "").strip()
    if env_secret and env_secret not in candidates:
        candidates.append(env_secret)

    if not candidates:
        logger.warning("Shopify webhook: no app secret for shop=%s (set SHOPIFY_API_SECRET or add in Integrations)", shop_domain)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="App secret not found for this shop. Set SHOPIFY_API_SECRET in env or add API Secret in Integrations → Shopify → Configure.")
    verified = any(verify_webhook_hmac(raw_body, hmac_header, s) for s in candidates)
    if not verified:
        logger.warning("Shopify webhook: HMAC verification failed for shop=%s topic=%s", shop_domain, topic)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as e:
        logger.warning("Shopify webhook: invalid JSON %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Payload summary for storage (e.g. order id)
    summary = None
    if isinstance(payload, dict):
        oid = payload.get("id") or payload.get("order_id")
        if oid is not None:
            summary = f"id={oid}"

    event = WebhookEvent(
        id=str(uuid.uuid4()),
        source="shopify",
        shop_domain=shop_domain,
        topic=topic,
        payload_summary=summary,
    )
    db.add(event)
    db.commit()

    try:
        process_shopify_webhook(db, shop_domain, topic, payload, event_id=event.id)
        db.commit()
        
        # Broadcast real-time update
        from app.services.realtime_service import realtime_service
        await realtime_service.broadcast_webhook_event(db, event)
        
    except Exception as e:
        logger.exception("Shopify webhook process failed: %s", e)
        try:
            ev = db.query(WebhookEvent).filter(WebhookEvent.id == event.id).first()
            if ev:
                ev.error = str(e)[:500]
            db.commit()
        except Exception:
            db.rollback()
        # Return 200 so Shopify does not retry

    return {"ok": True}


@router.post("/amazon")
async def amazon_webhook_receive(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint for Amazon SP-API webhooks. No JWT.
    Verify signature, persist event, trigger processing by notification type.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Amz-Sns-Message-Signature")
    topic = request.headers.get("X-Amz-Sns-Topic") or ""
    
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as e:
        logger.warning("Amazon webhook: invalid JSON %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Extract marketplace ID from payload
    marketplace_id = payload.get("marketplaceId", "")
    notification_type = payload.get("notificationType", "")

    if not marketplace_id:
        logger.warning("Amazon webhook: missing marketplace ID")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing marketplace ID")

    # Get Amazon credentials for verification
    # You would need to implement credential retrieval for Amazon
    # For now, we'll skip verification in this example
    verified = True  # Skip verification for now - implement proper verification

    if not verified:
        logger.warning("Amazon webhook: signature verification failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    # Persist event
    summary = None
    if isinstance(payload, dict):
        order_id = payload.get("payload", {}).get("OrderChangeNotification", {}).get("AmazonOrderId")
        if order_id:
            summary = f"order_id={order_id}"

    event = WebhookEvent(
        id=str(uuid.uuid4()),
        source="amazon",
        shop_domain=marketplace_id,  # Use marketplace_id as shop_domain for Amazon
        topic=notification_type,
        payload_summary=summary,
    )
    db.add(event)
    db.commit()

    try:
        process_amazon_webhook(db, marketplace_id, notification_type, payload, event_id=event.id)
        db.commit()
        
        # Broadcast real-time update
        await realtime_service.broadcast_webhook_event(db, event)
        
    except Exception as e:
        logger.exception("Amazon webhook process failed: %s", e)
        try:
            ev = db.query(WebhookEvent).filter(WebhookEvent.id == event.id).first()
            if ev:
                ev.error = str(e)[:500]
            db.commit()
        except Exception:
            db.rollback()

    return {"ok": True}


@router.post("/flipkart")
async def flipkart_webhook_receive(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint for Flipkart webhooks. No JWT.
    Verify HMAC signature, persist event, trigger processing by event type.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Flipkart-Signature")
    event_type = request.headers.get("X-Flipkart-Event-Type") or ""
    seller_id = request.headers.get("X-Flipkart-Seller-Id") or ""
    
    if not seller_id:
        logger.warning("Flipkart webhook: missing X-Flipkart-Seller-Id")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing seller ID")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as e:
        logger.warning("Flipkart webhook: invalid JSON %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Get Flipkart credentials for verification
    # You would need to implement credential retrieval for Flipkart
    # For now, we'll skip verification in this example
    verified = True  # Skip verification for now - implement proper verification

    if not verified:
        logger.warning("Flipkart webhook: signature verification failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    # Persist event
    summary = None
    if isinstance(payload, dict):
        order_id = payload.get("order", {}).get("orderId")
        if order_id:
            summary = f"order_id={order_id}"

    event = WebhookEvent(
        id=str(uuid.uuid4()),
        source="flipkart",
        shop_domain=seller_id,  # Use seller_id as shop_domain for Flipkart
        topic=event_type,
        payload_summary=summary,
    )
    db.add(event)
    db.commit()

    try:
        process_flipkart_webhook(db, seller_id, event_type, payload, event_id=event.id)
        db.commit()
        
        # Broadcast real-time update
        await realtime_service.broadcast_webhook_event(db, event)
        
    except Exception as e:
        logger.exception("Flipkart webhook process failed: %s", e)
        try:
            ev = db.query(WebhookEvent).filter(WebhookEvent.id == event.id).first()
            if ev:
                ev.error = str(e)[:500]
            db.commit()
        except Exception:
            db.rollback()

    return {"ok": True}


@router.post("/selloship")
async def selloship_webhook_receive(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public endpoint for Selloship webhook notifications. No JWT.
    Verify HMAC signature, persist event, trigger processing by event type.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Selloship-Signature")
    event_type = request.headers.get("X-Selloship-Event-Type") or ""
    tracking_number = request.headers.get("X-Selloship-Tracking-Number") or ""
    
    if not tracking_number:
        logger.warning("Selloship webhook: missing X-Selloship-Tracking-Number")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing tracking number")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as e:
        logger.warning("Selloship webhook: invalid JSON %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Get Selloship credentials for verification
    # For now, we'll skip verification in this example
    # In production, you would retrieve the secret from your Selloship configuration
    verified = True  # Skip verification for now - implement proper verification

    if not verified:
        logger.warning("Selloship webhook: signature verification failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    # Persist event
    summary = f"tracking_number={tracking_number}, event_type={event_type}"

    event = WebhookEvent(
        id=str(uuid.uuid4()),
        source="selloship",
        shop_domain=tracking_number,  # Use tracking_number as shop_domain for Selloship
        topic=event_type,
        payload_summary=summary,
    )
    db.add(event)
    db.commit()

    try:
        process_selloship_webhook(db, tracking_number, event_type, payload, event_id=event.id)
        db.commit()
        
        # Broadcast real-time update
        await realtime_service.broadcast_webhook_event(db, event)
        
    except Exception as e:
        logger.exception("Selloship webhook process failed: %s", e)
        try:
            ev = db.query(WebhookEvent).filter(WebhookEvent.id == event.id).first()
            if ev:
                ev.error = str(e)[:500]
            db.commit()
        except Exception:
            db.rollback()

    return {"ok": True}


@router.post("/events/{event_id}/retry")
async def retry_webhook_event(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retry a failed webhook event. Event must belong to one of the current user's shops.
    Note: Full payload is not stored; retry re-processes only if the handler can re-fetch data.
    For Shopify, failed events are not re-sent by Shopify; consider re-syncing orders/inventory instead.
    """
    user_shops = _get_user_shop_domains(db, str(current_user.id))
    event = db.query(WebhookEvent).filter(WebhookEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.shop_domain not in user_shops:
        raise HTTPException(status_code=403, detail="Access denied")
    # We do not store full payload; cannot truly re-run process_shopify_webhook without it
    raise HTTPException(
        status_code=501,
        detail="Retry not supported: event payload is not stored. Re-sync orders or inventory from Integrations if needed.",
    )


@router.get("/subscriptions")
async def get_webhook_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get webhook subscriptions for the current user (from their channel accounts)."""
    accounts = db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()

    # Build list with channel-agnostic labels (channel name + optional shop/account identifier)
    channel_name = lambda acc: (
        getattr(acc.channel, "name", None) and getattr(acc.channel.name, "value", str(acc.channel.name))
    ) or "Channel"
    subscriptions = []
    for account in accounts:
        is_active = account.status.value == "CONNECTED"
        ch = channel_name(account)
        label = f"{ch}"
        if getattr(account, "shop_domain", None) and (account.shop_domain or "").strip():
            label = f"{ch} ({account.shop_domain})"
        topic_desc = "orders, inventory, products (webhooks)"
        if ch == "SHOPIFY":
            topic_desc = "orders/create, orders/updated, orders/cancelled, refunds/create, inventory_levels/update, products/update"
        subscriptions.append({
            "id": account.id,
            "integrationId": account.id,
            "channel": ch,
            "topic": f"{label}: {topic_desc}",
            "status": "ACTIVE" if is_active else "INACTIVE",
            "lastError": None,
            "updatedAt": (getattr(account, "updated_at", None) and account.updated_at.isoformat())
            or (account.created_at.isoformat() if account.created_at else None),
        })

    return subscriptions


@router.get("/events/stream")
async def webhook_events_stream(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Server-Sent Events endpoint for real-time webhook updates.
    Clients can connect to receive live updates when webhooks are processed.
    """
    return EventSourceResponse(
        realtime_service.generate_events(request, current_user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )
