"""
LaCleoOmnia OMS - FastAPI Backend
"""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi import status
from sqlalchemy.orm import Session
import uvicorn
import logging

from routes.api import register_routes
from app.database import engine, Base, get_db, SessionLocal
from app.config import settings
from app.services.shopify_oauth import ShopifyOAuthService
from app.services.shipment_sync import sync_shipments
from app.services.ad_spend_sync import sync_ad_spend_for_date, get_first_user_id_for_sync
from app.services.credentials import encrypt_token, decrypt_token
from app.models import (
    User,
    Channel,
    ChannelAccount,
    ChannelType,
    ChannelAccountStatus,
    ProviderCredential,
    ShopifyIntegration,
    AuditLog,
    AuditLogAction,
    Order,
)
from app.services.profit_calculator import compute_profit_for_order
from sqlalchemy import func
from jose import jwt, JWTError
import json
import time

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="LaCleoOmnia OMS API",
    description="Order Management System API",
    version="1.0.0",
    docs_url="/docs" if settings.IS_DEVELOPMENT else None,  # Disable docs in production
    redoc_url="/redoc" if settings.IS_DEVELOPMENT else None,  # Disable redoc in production
)

# Log startup information
logger.info(f"🚀 Starting LaCleoOmnia API")
logger.info(f"📊 Environment: {settings.ENV}")
logger.info(f"🌐 Production: {settings.IS_PRODUCTION}")
logger.info(f"☁️  Cloud: {settings.IS_CLOUD}")
logger.info(f"🔗 Host: {settings.HOST}:{settings.PORT}")

# Startup config validation (warn only)
if settings.IS_PRODUCTION and getattr(settings, "JWT_SECRET", "").strip() in ("", "supersecret_fallback_key_change_in_production"):
    logger.warning("⚠️ JWT_SECRET is default or empty in production. Set a strong JWT_SECRET in environment.")
if not (getattr(settings, "DATABASE_URL", "") or "").strip():
    logger.warning("⚠️ DATABASE_URL is not set. Database operations will fail.")
if settings.IS_PRODUCTION and not (os.getenv("ALLOWED_ORIGINS", "") or "").strip():
    logger.warning("⚠️ ALLOWED_ORIGINS is not set in production. Set your frontend origin(s) (comma-separated) to avoid CORS issues.")

def get_cors_headers(request: Request) -> dict:
    """Get CORS headers for a request"""
    origin = request.headers.get("origin", "")
    allowed_origins = settings.ALLOWED_ORIGINS
    
    # Check if origin is in allowed list
    if origin in allowed_origins:
        cors_origin = origin
    elif settings.IS_DEVELOPMENT and (origin.startswith("http://localhost") or origin.startswith("http://127.0.0.1")):
        # Allow localhost in development
        cors_origin = origin
    elif allowed_origins:
        # Use first allowed origin as fallback
        cors_origin = allowed_origins[0]
    else:
        cors_origin = "*"
    
    return {
        "Access-Control-Allow-Origin": cors_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

# Add exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": exc.errors(),
            "message": "Validation error: Please check your request format"
        },
        headers=get_cors_headers(request)
    )

# Add exception handler for HTTPException to ensure CORS headers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPException and ensure CORS headers are sent"""
    headers = get_cors_headers(request)
    # Preserve any existing headers from the exception
    if exc.headers:
        headers.update(exc.headers)
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers
    )

# Add global exception handler to ensure CORS headers are always sent
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to ensure CORS headers are always sent"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": str(exc) if settings.IS_DEVELOPMENT else "An error occurred"
        },
        headers=get_cors_headers(request)
    )

# CORS configuration - Fully dynamic based on ALLOWED_ORIGINS environment variable
cors_kwargs = {
    "allow_origins": settings.ALLOWED_ORIGINS,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["*"],
    "expose_headers": ["*"],
}

# Only add regex if it's set (not None)
cors_regex = settings.CORS_ORIGIN_REGEX
if cors_regex:
    cors_kwargs["allow_origin_regex"] = cors_regex

app.add_middleware(CORSMiddleware, **cors_kwargs)

logger.info(f"✅ CORS configured for {len(settings.ALLOWED_ORIGINS)} origin(s)")
if cors_regex:
    logger.info(f"   + Regex pattern: {cors_regex}")
logger.info(f"   Allowed origins: {settings.ALLOWED_ORIGINS}")

# Register all API routes (prefix /api; paths unchanged)
register_routes(app, settings)

@app.get("/health")
async def health():
    """Health check endpoint. Includes DB connectivity check."""
    db_status = "ok"
    try:
        from app.database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("Health check DB ping failed: %s", e)
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": "api",
        "db": db_status,
        "environment": settings.ENV,
        "production": settings.IS_PRODUCTION,
        "cloud": settings.IS_CLOUD,
    }


# --- Unified courier 30-min poll: Delhivery + Selloship, RTO/Lost → profit recalc ---
SHIPMENT_POLL_INTERVAL_SEC = int(os.getenv("SHIPMENT_POLL_INTERVAL_SEC", "1800"))  # 30 min
SHIPMENT_POLL_FIRST_DELAY_SEC = int(os.getenv("SHIPMENT_POLL_FIRST_DELAY_SEC", "120"))  # first run after 2 min


async def _shipments_sync_loop() -> None:
    """Background: poll Delhivery and Selloship every 30 min; update status/cost; trigger profit recalc. Single loop."""
    await asyncio.sleep(SHIPMENT_POLL_FIRST_DELAY_SEC)
    logger.info("Shipments 30-min poll started (interval=%ss)", SHIPMENT_POLL_INTERVAL_SEC)
    while True:
        db = None
        try:
            db = SessionLocal()
            result = await sync_shipments(db, user_id=None)
            if result.get("synced", 0) > 0 or result.get("errors"):
                logger.info("Shipments sync: synced=%s errors=%s", result.get("synced", 0), len(result.get("errors", [])))
        except Exception as e:
            logger.exception("Shipments 30-min sync failed: %s", e)
        finally:
            if db:
                db.close()
        await asyncio.sleep(SHIPMENT_POLL_INTERVAL_SEC)


@app.on_event("startup")
async def startup_shipments_poll() -> None:
    """Start background unified courier sync loop (every 30 min)."""
    asyncio.create_task(_shipments_sync_loop())


# --- Ad spend daily sync at 00:30 IST (CAC) ---
IST = timezone(timedelta(hours=5, minutes=30))


def _seconds_until_0030_ist() -> float:
    """Seconds until next 00:30 IST (or 0 if within 60s of it)."""
    now_ist = datetime.now(IST)
    target = now_ist.replace(hour=0, minute=30, second=0, microsecond=0)
    if now_ist >= target:
        target += timedelta(days=1)
    delta = (target - now_ist).total_seconds()
    return max(0, delta)


async def _ad_spend_sync_loop() -> None:
    """Background: every day at 00:30 IST, sync yesterday's Meta + Google ad spend for CAC."""
    logger.info("Ad spend daily sync scheduled (00:30 IST)")
    while True:
        secs = _seconds_until_0030_ist()
        if secs > 60:
            await asyncio.sleep(min(secs, 3600))  # wait until 00:30 IST, cap 1h for quick startup
        db = None
        try:
            db = SessionLocal()
            user_id = get_first_user_id_for_sync(db)
            if not user_id:
                logger.debug("Ad spend sync: no meta_ads/google_ads credentials; skip")
            else:
                now_ist = datetime.now(IST)
                yesterday = (now_ist - timedelta(days=1)).date()
                result = await sync_ad_spend_for_date(db, user_id, yesterday)
                db.commit()
                for (oid,) in db.query(Order.id).filter(func.date(Order.created_at) == yesterday).all():
                    compute_profit_for_order(db, str(oid))
                db.commit()
                if result.get("meta") or result.get("google") or result.get("errors"):
                    logger.info("Ad spend sync: date=%s meta=%s google=%s errors=%s",
                                yesterday, result.get("meta"), result.get("google"), result.get("errors"))
        except Exception as e:
            logger.exception("Ad spend daily sync failed: %s", e)
        finally:
            if db:
                db.close()
        # Next run: next day 00:30 IST
        await asyncio.sleep(_seconds_until_0030_ist() + 60)


@app.on_event("startup")
async def startup_ad_spend_sync() -> None:
    """Start background ad spend sync (daily at 00:30 IST)."""
    asyncio.create_task(_ad_spend_sync_loop())


def _get_frontend_url() -> str:
    """Redirect URL after OAuth. Prefer ALLOWED_ORIGINS or FRONTEND_URL; fallback to LaCleoOmnia dashboard."""
    if settings.ALLOWED_ORIGINS:
        return settings.ALLOWED_ORIGINS[0].rstrip("/")
    if settings.IS_CLOUD:
        return os.getenv("FRONTEND_URL") or os.getenv("NEXT_PUBLIC_URL") or "https://la-cleo-omnia-web.vercel.app"
    return os.getenv("FRONTEND_URL") or "http://localhost:3000"


def _shopify_app_url_redirect(request: Request) -> RedirectResponse | None:
    """If this is a Shopify App install redirect (shop in query), redirect to frontend /auth/shopify."""
    shop = request.query_params.get("shop")
    if not shop:
        return None
    frontend_url = _get_frontend_url()
    # Preserve shop, host, hmac, timestamp for frontend
    from urllib.parse import urlencode
    params = {"shop": shop}
    for key in ("host", "hmac", "timestamp"):
        if request.query_params.get(key):
            params[key] = request.query_params.get(key)
    to_url = f"{frontend_url}/auth/shopify?{urlencode(params)}"
    return RedirectResponse(url=to_url, status_code=302)


@app.get("/auth/shopify")
async def auth_shopify_app_url(
    request: Request,
):
    """
    Shopify App URL handler. When Shopify redirects the merchant here after clicking Install,
    redirect to the frontend so the user can log in (if needed) and complete OAuth.
    Set this as your App URL in Shopify: https://<YOUR_API_BASE>/auth/shopify
    """
    r = _shopify_app_url_redirect(request)
    if r is not None:
        return r
    frontend_url = _get_frontend_url()
    return RedirectResponse(url=f"{frontend_url}/dashboard/integrations", status_code=302)


@app.get("/")
async def root_app_url(request: Request):
    """
    Root handler. If Shopify sends ?shop=... (App URL set to API root), redirect to frontend /auth/shopify.
    Otherwise return a short message so API root does not 404.
    """
    r = _shopify_app_url_redirect(request)
    if r is not None:
        return r
    return JSONResponse(
        content={
            "message": "LaCleoOmnia API",
            "version": "1.0.0",
            "docs": "/docs" if settings.IS_DEVELOPMENT else None,
            "health": "/health",
        }
    )


@app.get(
    "/auth/shopify/callback",
    summary="Shopify OAuth callback: HMAC verify, token exchange, persist, redirect",
)
async def auth_shopify_callback(
    request: Request,
    shop: str = Query(None),
    code: str = Query(None),
    hmac: str = Query(None),
    state: str = Query(None),
    timestamp: str = Query(None),
    db: Session = Depends(get_db),
):
    """
    Receives shop, hmac, timestamp, code from Shopify.
    Verifies HMAC, exchanges code for access_token, saves/updates shopify_integrations, redirects to dashboard.
    """
    raw_query = request.url.query or ""
    frontend_url = _get_frontend_url()
    redirect_fail = f"{frontend_url}/dashboard/integrations?error=oauth_failed"
    redirect_ok = f"{frontend_url}/dashboard/integrations?shopify=connected"

    def _fail(msg: str) -> RedirectResponse:
        logger.warning("Shopify OAuth callback: %s", msg)
        return RedirectResponse(url=redirect_fail)

    try:
        if not raw_query or not shop or not code:
            return RedirectResponse(
                url=f"{frontend_url}/dashboard/integrations?error=missing_params" if not raw_query else f"{frontend_url}/dashboard/integrations?error=missing_shop_or_code"
            )

        api_key = None
        api_secret = None
        user_id = None
        if state:
            try:
                state_data = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.AUTH_ALGORITHM])
                user_id = state_data.get("user_id")
                if user_id is not None:
                    user_id = str(user_id).strip()
                if user_id:
                    cred = db.query(ProviderCredential).filter(
                        ProviderCredential.user_id == user_id,
                        ProviderCredential.provider_id == "shopify_app",
                    ).first()
                    if cred and cred.value_encrypted:
                        dec = decrypt_token(cred.value_encrypted)
                        data = json.loads(dec) if isinstance(dec, str) and dec.strip().startswith("{") else {}
                        if isinstance(data, dict) and data.get("apiKey") and data.get("apiSecret"):
                            api_key = (data.get("apiKey") or "").strip()
                            api_secret = (data.get("apiSecret") or "").strip()
            except (JWTError, Exception) as e:
                logger.debug("State decode or cred load: %s", e)

        if not api_key or not api_secret:
            if user_id:
                return RedirectResponse(url=f"{frontend_url}/dashboard/integrations?error=shopify_creds_required")
            return _fail("no credentials in state")

        oauth_service = ShopifyOAuthService(api_key=api_key, api_secret=api_secret)
        if not oauth_service.verify_hmac(raw_query):
            return _fail("HMAC verification failed")

        try:
            normalized_shop = oauth_service.normalize_shop_domain(shop)
        except ValueError as e:
            return _fail(f"invalid shop domain: {e}")

        try:
            token_data = await oauth_service.exchange_code_for_token(normalized_shop, code)
        except Exception as e:
            logger.exception("Token exchange failed: %s", e)
            return RedirectResponse(url=redirect_fail)

        access_token = token_data.get("access_token")
        scopes = (token_data.get("scope") or "") or ""
        if access_token is None or (isinstance(access_token, str) and not access_token.strip()):
            return _fail("no access_token in Shopify response")
        access_token = str(access_token).strip()

        existing_int = db.query(ShopifyIntegration).filter(
            ShopifyIntegration.shop_domain == normalized_shop,
        ).first()
        app_secret_encrypted = encrypt_token(api_secret) if api_secret else None
        if existing_int:
            existing_int.access_token = access_token
            existing_int.scopes = scopes
            existing_int.app_secret_encrypted = app_secret_encrypted
            logger.info("Updated Shopify integration for shop: %s", normalized_shop)
        else:
            db.add(ShopifyIntegration(
                shop_domain=normalized_shop,
                access_token=access_token,
                scopes=scopes,
                app_secret_encrypted=app_secret_encrypted,
            ))
            logger.info("Created Shopify integration for shop: %s", normalized_shop)

        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                channel = db.query(Channel).filter(Channel.name == ChannelType.SHOPIFY).first()
                if not channel:
                    channel = Channel(name=ChannelType.SHOPIFY, is_active=True)
                    db.add(channel)
                    db.flush()
                acc = db.query(ChannelAccount).filter(
                    ChannelAccount.channel_id == channel.id,
                    ChannelAccount.user_id == user_id,
                    ChannelAccount.shop_domain == normalized_shop,
                ).first()
                shop_name = normalized_shop
                if acc:
                    acc.access_token = encrypt_token(access_token)
                    acc.status = ChannelAccountStatus.CONNECTED
                else:
                    acc = ChannelAccount(
                        channel_id=channel.id,
                        user_id=user_id,
                        seller_name=shop_name,
                        shop_domain=normalized_shop,
                        access_token=encrypt_token(access_token),
                        status=ChannelAccountStatus.CONNECTED,
                    )
                    db.add(acc)
                    db.flush()
                audit = AuditLog(
                    user_id=user_id,
                    action=AuditLogAction.INTEGRATION_CONNECTED,
                    entity_type="Integration",
                    entity_id=acc.id,
                    details={"channel": "SHOPIFY", "shop_domain": normalized_shop},
                )
                db.add(audit)

        db.commit()
        return RedirectResponse(url=redirect_ok)
    except Exception as e:
        logger.exception("Shopify OAuth callback unhandled error: %s", e)
        return RedirectResponse(url=f"{frontend_url}/dashboard/integrations?error=oauth_failed")

@app.get("/api")
async def root():
    """API root endpoint"""
    return {
        "message": "Welcome to LaCleoOmnia Unitecommerce API",
        "version": "1.0.0",
        "environment": settings.ENV,
        "docs": "/docs" if settings.IS_DEVELOPMENT else "disabled in production"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.IS_DEVELOPMENT,  # Auto-reload only in development
        log_level=settings.LOG_LEVEL.lower()
    )
