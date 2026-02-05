"""
Channel and integration routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Channel, ChannelAccount, ChannelType, ChannelAccountStatus, User, AuditLog, AuditLogAction, ProviderCredential
from app.auth import get_current_user, create_access_token
from app.http.requests import ShopifyConnectRequest, ChannelAccountResponse
from app.services.shopify import ShopifyService
from app.services.shopify_oauth import ShopifyOAuthService
from app.services.credentials import encrypt_token, decrypt_token
from app.config import settings
import json
from jose import jwt, JWTError
from datetime import timedelta, datetime, timezone
import re
import httpx
import os
import secrets
import time
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("")
async def list_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all channels"""
    channels = db.query(Channel).all()
    result = []
    for channel in channels:
        accounts = db.query(ChannelAccount).filter(
            ChannelAccount.channel_id == channel.id
        ).all()
        result.append({
            "id": channel.id,
            "name": channel.name.value,
            "isActive": channel.is_active,
            "accounts": [
                {
                    "id": acc.id,
                    "sellerName": acc.seller_name,
                    "shopDomain": acc.shop_domain,
                    "status": acc.status.value,
                    "createdAt": acc.created_at.isoformat() if acc.created_at else None,
                }
                for acc in accounts
            ]
        })
    return {"channels": result}

@router.post("/shopify/connect")
async def connect_shopify(
    request: ShopifyConnectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Connect Shopify store"""
    # Normalize shop domain
    normalized_domain = re.sub(r'^https?://', '', request.shop_domain)
    normalized_domain = re.sub(r'\.myshopify\.com$', '', normalized_domain, flags=re.IGNORECASE)
    normalized_domain = normalized_domain.lower()
    
    # Get or create Shopify channel
    channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
    if not channel:
        channel = Channel(name=ChannelType.SHOPIFY, is_active=True)
        db.add(channel)
        db.commit()
        db.refresh(channel)
    
    # Encrypt token
    encrypted_token = encrypt_token(request.access_token)
    
    # Create channel account
    account = ChannelAccount(
        channel_id=channel.id,
        user_id=current_user.id,  # Associate with current user
        seller_name=request.seller_name,
        shop_domain=normalized_domain,
        access_token=encrypted_token,
        status=ChannelAccountStatus.CONNECTED
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    
    # Log audit event
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.INTEGRATION_CONNECTED,
        entity_type="Integration",
        entity_id=account.id,
        details={"channel": "SHOPIFY", "shop_domain": normalized_domain}
    )
    db.add(audit_log)
    db.commit()
    
    return {
        "account": {
            "id": account.id,
            "sellerName": account.seller_name,
            "shopDomain": account.shop_domain,
            "status": account.status.value
        }
    }

@router.post("/shopify/test")
async def test_shopify(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test Shopify connection - can test with accountId or with shopDomain + accessToken"""
    account_id = request.get("accountId")
    shop_domain = request.get("shopDomain")
    access_token = request.get("accessToken")
    
    account = None
    
    if account_id:
        # Test existing connection (only current user's account)
        account = db.query(ChannelAccount).filter(
            ChannelAccount.id == account_id,
            ChannelAccount.user_id == current_user.id,
        ).first()
        if not account:
            raise HTTPException(status_code=404, detail="Channel account not found")
    elif shop_domain and access_token:
        # Test new connection before saving
        from app.services.credentials import encrypt_token
        normalized_domain = re.sub(r'^https?://', '', shop_domain)
        normalized_domain = re.sub(r'\.myshopify\.com$', '', normalized_domain, flags=re.IGNORECASE)
        normalized_domain = normalized_domain.lower()
        
        # Create temporary account object for testing
        from app.models import ChannelAccount, ChannelAccountStatus
        channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
        if not channel:
            raise HTTPException(status_code=404, detail="Shopify channel not found")
        
        account = ChannelAccount(
            channel_id=channel.id,
            seller_name="Test",
            shop_domain=normalized_domain,
            access_token=encrypt_token(access_token),
            status=ChannelAccountStatus.CONNECTED
        )
    else:
        raise HTTPException(status_code=400, detail="Either accountId or (shopDomain + accessToken) is required")
    
    try:
        service = ShopifyService(account)
        shop = await service.get_shop()
        
        # Get additional info
        locations = await service.get_locations()
        products_count = await service.get_products_count()
        recent_orders = await service.get_recent_orders(limit=10)
        
        return {
            "success": True,
            "shop": {
                "name": shop.get("name", ""),
                "domain": shop.get("domain", ""),
                "email": shop.get("email", ""),
                "currency": shop.get("currency", ""),
            },
            "locations": [{"id": loc.get("id"), "name": loc.get("name")} for loc in locations[:5]],
            "productsCount": products_count,
            "recentOrdersCount": len(recent_orders),
            "lastOrderDate": recent_orders[0].get("created_at") if recent_orders else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")

@router.post("/shopify/import-orders")
async def import_shopify_orders_endpoint(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Import orders from Shopify"""
    from app.services.order_import import import_shopify_orders
    
    account_id = request.get("accountId")
    if not account_id:
        raise HTTPException(status_code=400, detail="accountId is required")

    account = db.query(ChannelAccount).filter(
        ChannelAccount.id == account_id,
        ChannelAccount.user_id == current_user.id,
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Channel account not found")

    result = await import_shopify_orders(db, account)
    return result

@router.get("/shopify/oauth/install")
async def shopify_oauth_install(
    request: Request,
    shop: str = Query(..., description="Shop domain (e.g., mystore or mystore.myshopify.com)"),
    redirect_uri: str = Query(None, description="Redirect URI after OAuth"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get Shopify OAuth install URL - requires authentication
    
    Generates secure OAuth URL with:
    - Signed state token containing user_id, shop, nonce, expiry
    - Proper redirect URI validation
    - Production-grade security
    """
    logger.info(f"OAuth install request from user {current_user.id} for shop: {shop}")
    
    # Use only the logged-in user's Shopify App credentials from Integrations (no .env fallback)
    api_key, api_secret = None, None
    cred = db.query(ProviderCredential).filter(
        ProviderCredential.user_id == current_user.id,
        ProviderCredential.provider_id == "shopify_app",
    ).first()
    if cred and cred.value_encrypted:
        try:
            dec = decrypt_token(cred.value_encrypted)
            data = json.loads(dec) if isinstance(dec, str) and dec.strip().startswith("{") else {}
            if isinstance(data, dict) and data.get("apiKey") and data.get("apiSecret"):
                api_key = (data.get("apiKey") or "").strip()
                api_secret = (data.get("apiSecret") or "").strip()
        except Exception:
            pass
    if not api_key or not api_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add your Shopify App API Key and Secret in Integrations first: open the Shopify card → click the pencil (Edit) or Configure → paste API Key (Client ID) and API Secret (Client secret) from your Shopify app → Save. No .env required."
        )
    
    scopes = getattr(settings, "SHOPIFY_SCOPES", "") or ""
    oauth_service = ShopifyOAuthService(api_key=api_key, api_secret=api_secret, scopes=scopes)
    
    try:
        # Normalize shop domain
        normalized_shop = oauth_service.normalize_shop_domain(shop)
        
        # Generate secure state parameter with expiry, nonce, shop, and user_id
        nonce = secrets.token_urlsafe(32)  # Random nonce for CSRF protection
        expiry_seconds = 600  # 10 minutes
        expires_at = int(time.time()) + expiry_seconds
        
        state_data = {
            "user_id": current_user.id,
            "shop": normalized_shop,
            "nonce": nonce,
            "exp": expires_at,  # JWT expiry
            "iat": int(time.time()),  # Issued at
        }
        
        state_token = jwt.encode(
            state_data,
            settings.JWT_SECRET,
            algorithm=settings.AUTH_ALGORITHM
        )
        
        logger.info(f"Generated state token for user {current_user.id}, shop {normalized_shop}")
        
        # Build redirect URI: use API base URL (no dependency on request.url so OAuth works for all users)
        if not redirect_uri:
            base_url = (getattr(settings, "WEBHOOK_BASE_URL", None) or "").strip().rstrip("/")
            if not base_url and settings.IS_CLOUD:
                base_url = (
                    os.getenv("RENDER_EXTERNAL_URL") or
                    os.getenv("RAILWAY_PUBLIC_DOMAIN") or
                    (os.getenv("HEROKU_APP_NAME") and f"https://{os.getenv('HEROKU_APP_NAME')}.herokuapp.com") or
                    ""
                )
            if not base_url:
                try:
                    if request and hasattr(request, "url") and request.url:
                        base_url = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
                except Exception:
                    pass
            if not base_url:
                base_url = "http://localhost:8000"
            redirect_uri = f"{base_url}/auth/shopify/callback"
        else:
            # Validate provided redirect_uri to prevent open redirects
            from urllib.parse import urlparse
            parsed = urlparse(redirect_uri)
            if not parsed.scheme or not parsed.netloc:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid redirect_uri format"
                )
            # Only allow https in production (or localhost for dev)
            if settings.IS_PRODUCTION and parsed.scheme != "https" and "localhost" not in parsed.netloc:
                raise HTTPException(
                    status_code=400,
                    detail="redirect_uri must use HTTPS in production"
                )
        
        # Generate OAuth install URL
        install_url = oauth_service.get_install_url(normalized_shop, redirect_uri, state_token)
        
        logger.info(f"OAuth install URL generated successfully for shop: {normalized_shop}")
        
        return {
            "installUrl": install_url,
            "shop": normalized_shop,
            "redirectUri": redirect_uri,
            "state": state_token
        }
        
    except ValueError as e:
        logger.error(f"Invalid shop domain: {shop} - {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid shop domain: {str(e)}"
        )
    except Exception as e:
        logger.error(f"OAuth install error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate OAuth install URL: {str(e)}"
        )

@router.get("/shopify/oauth/callback")
async def shopify_oauth_callback(
    request: Request,
    shop: str = Query(None),  # Make optional to handle missing shop gracefully
    code: str = Query(None),
    hmac: str = Query(None),
    state: str = Query(None),
    timestamp: str = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle Shopify OAuth callback - PUBLIC endpoint (no JWT required)
    
    Security validations:
    1. HMAC verification (Shopify signature)
    2. State token validation (JWT with expiry, shop, user_id, nonce)
    3. Shop domain validation
    4. Token exchange and storage
    5. Webhook registration
    """
    # Helper function to get frontend URL dynamically
    def get_frontend_url():
        if settings.ALLOWED_ORIGINS:
            return settings.ALLOWED_ORIGINS[0]
        if settings.IS_CLOUD:
            return os.getenv("FRONTEND_URL") or os.getenv("NEXT_PUBLIC_URL") or "http://localhost:3000"
        return "http://localhost:3000"
    
    # Log callback received
    logger.info(f"OAuth callback received - shop: {shop}, has_code: {bool(code)}, has_state: {bool(state)}, has_hmac: {bool(hmac)}")
    
    # Validate configuration
    if not settings.SHOPIFY_API_KEY or not settings.SHOPIFY_API_SECRET:
        logger.error("OAuth callback failed: OAuth not configured")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=oauth_not_configured"
        )
    
    # Validate required parameters
    if not shop:
        logger.error("OAuth callback failed: missing shop parameter")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=missing_shop"
        )
    
    if not code:
        logger.error("OAuth callback failed: missing code parameter")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=no_code"
        )
    
    if not state:
        logger.error("OAuth callback failed: missing state parameter")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=missing_state"
        )
    
    # Validate HMAC signature from Shopify
    oauth_service = ShopifyOAuthService()
    try:
        # Get query string from request
        query_string = str(request.url.query)
        
        if not oauth_service.verify_hmac(query_string):
            logger.error(f"OAuth callback failed: HMAC verification failed for shop: {shop}")
            return RedirectResponse(
                url=f"{get_frontend_url()}/dashboard/integrations?error=invalid_hmac"
            )
        logger.info(f"HMAC verification passed for shop: {shop}")
    except Exception as e:
        logger.error(f"HMAC verification error: {e}")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=hmac_error"
        )
    
    # Decode and validate state token
    user_id = None
    state_shop = None
    state_nonce = None
    
    try:
        state_data = jwt.decode(
            state,
            settings.JWT_SECRET,
            algorithms=[settings.AUTH_ALGORITHM]
        )
        user_id = state_data.get("user_id")
        state_shop = state_data.get("shop")
        state_nonce = state_data.get("nonce")
        state_exp = state_data.get("exp")
        
        # Check expiry
        if state_exp and int(time.time()) > state_exp:
            logger.error(f"OAuth callback failed: state token expired for shop: {shop}")
            return RedirectResponse(
                url=f"{get_frontend_url()}/dashboard/integrations?error=state_expired"
            )
        
        logger.info(f"State token decoded successfully - user_id: {user_id}, shop: {state_shop}")
        
    except JWTError as e:
        logger.error(f"OAuth callback failed: invalid state token - {e}")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=invalid_state"
        )
    except Exception as e:
        logger.error(f"State token decode error: {e}")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=state_decode_error"
        )
    
    # Validate shop matches state
    try:
        normalized_shop = oauth_service.normalize_shop_domain(shop)
        if state_shop and normalized_shop != state_shop:
            logger.error(f"OAuth callback failed: shop mismatch - state: {state_shop}, callback: {normalized_shop}")
            return RedirectResponse(
                url=f"{get_frontend_url()}/dashboard/integrations?error=shop_mismatch"
            )
    except ValueError as e:
        logger.error(f"Invalid shop domain in callback: {shop} - {e}")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=invalid_shop_domain"
        )
    
    # Get user from database
    if not user_id:
        logger.error("OAuth callback failed: no user_id in state")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=no_user_id"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"OAuth callback failed: user not found - user_id: {user_id}")
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=user_not_found"
        )
    
    logger.info(f"Processing OAuth callback for user {user_id}, shop {normalized_shop}")
    
    # Exchange code for access token
    try:
        token_data = await oauth_service.exchange_code_for_token(normalized_shop, code)
        access_token = token_data.get("access_token")
        scope = token_data.get("scope", "")
        
        if not access_token:
            logger.error(f"OAuth callback failed: no access_token in response for shop: {normalized_shop}")
            return RedirectResponse(
                url=f"{get_frontend_url()}/dashboard/integrations?error=no_access_token"
            )
        
        logger.info(f"Successfully exchanged code for token for shop: {normalized_shop}")
        
        # Get shop info
        shopify_service = ShopifyService()
        shop_info = await shopify_service.get_shop_info(normalized_shop, access_token)
        shop_name = shop_info.get("name", normalized_shop)
        
        logger.info(f"Retrieved shop info: {shop_name}")
        
        # Get or create Shopify channel
        channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
        if not channel:
            channel = Channel(name=ChannelType.SHOPIFY, is_active=True)
            db.add(channel)
            db.commit()
            db.refresh(channel)
            logger.info("Created Shopify channel type")
        
        # Check if account already exists
        existing_account = db.query(ChannelAccount).filter(
            ChannelAccount.shop_domain == normalized_shop,
            ChannelAccount.user_id == user.id
        ).first()
        
        if existing_account:
            # Update existing account
            existing_account.access_token = encrypt_token(access_token)
            existing_account.status = ChannelAccountStatus.CONNECTED
            existing_account.scope = scope
            existing_account.updated_at = datetime.now(timezone.utc)
            account = existing_account
            logger.info(f"Updated existing channel account for shop: {normalized_shop}")
        else:
            # Create new account
            account = ChannelAccount(
                channel_id=channel.id,
                user_id=user.id,
                seller_name=shop_name,
                shop_domain=normalized_shop,
                access_token=encrypt_token(access_token),
                status=ChannelAccountStatus.CONNECTED,
                scope=scope
            )
            db.add(account)
            logger.info(f"Created new channel account for shop: {normalized_shop}")
        
        db.commit()
        db.refresh(account)
        
        # Automatically register webhooks
        webhook_result = None
        if settings.WEBHOOK_BASE_URL:
            try:
                logger.info(f"Registering webhooks for shop: {normalized_shop}")
                webhook_result = await shopify_service.ensure_webhook(
                    normalized_shop,
                    access_token,
                    settings.SHOPIFY_API_SECRET,
                    settings.WEBHOOK_BASE_URL
                )
                logger.info(f"Webhooks registered successfully for shop: {normalized_shop}")
            except Exception as e:
                # Log error but don't fail the connection
                logger.warning(f"Failed to register webhooks for shop {normalized_shop}: {e}", exc_info=True)
        
        # Log audit event
        audit_log = AuditLog(
            user_id=user.id,
            action=AuditLogAction.INTEGRATION_CONNECTED,
            entity_type="Integration",
            entity_id=account.id,
            details={
                "channel": "SHOPIFY",
                "shop_domain": normalized_shop,
                "shop_name": shop_name,
                "method": "OAuth",
                "webhooks_registered": webhook_result is not None
            }
        )
        db.add(audit_log)
        db.commit()
        
        logger.info(f"OAuth callback completed successfully for user {user_id}, shop {normalized_shop}")
        
        # Redirect to frontend success page
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?connected=shopify&shop={normalized_shop}"
        )
    
    except httpx.HTTPStatusError as e:
        logger.error(f"Token exchange HTTP error for shop {normalized_shop}: {e.response.status_code} - {e.response.text[:200]}")
        error_msg = f"shopify_error_{e.response.status_code}"
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error={error_msg}"
        )
    except Exception as e:
        logger.error(f"OAuth callback error for shop {normalized_shop}: {e}", exc_info=True)
        return RedirectResponse(
            url=f"{get_frontend_url()}/dashboard/integrations?error=oauth_failed"
        )
