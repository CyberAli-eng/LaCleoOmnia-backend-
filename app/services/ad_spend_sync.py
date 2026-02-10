"""
Daily ad spend sync: fetch Meta + Google Ads for a date, upsert ad_spend_daily.
Used by cron at 00:30 IST to sync yesterday's spend for CAC.
"""
import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models import AdSpendDaily, ProviderCredential, User
from app.services.credentials import decrypt_token
from app.services.meta_ads_service import fetch_meta_spend_for_date
from app.services.google_ads_service import fetch_google_spend_for_date

logger = logging.getLogger(__name__)

# Default USD to INR for Meta spend (account often in USD). Override with USD_TO_INR env.
DEFAULT_USD_TO_INR = Decimal("83")


def _get_meta_credentials(db: Session, user_id: str) -> Optional[dict]:
    """Return { ad_account_id, access_token } for meta_ads or None."""
    cred = db.query(ProviderCredential).filter(
        ProviderCredential.user_id == user_id,
        ProviderCredential.provider_id == "meta_ads",
    ).first()
    if not cred or not cred.value_encrypted:
        return None
    try:
        dec = decrypt_token(cred.value_encrypted)
        data = json.loads(dec) if isinstance(dec, str) and dec.strip().startswith("{") else {}
        if isinstance(data, dict) and data.get("access_token"):
            return {
                "ad_account_id": (data.get("ad_account_id") or data.get("adAccountId") or "").strip(),
                "access_token": (data.get("access_token") or data.get("accessToken") or "").strip(),
            }
    except Exception:
        pass
    return None


def _get_google_credentials(db: Session, user_id: str) -> Optional[dict]:
    """Return { developer_token, client_id, client_secret, refresh_token, customer_id } or None."""
    cred = db.query(ProviderCredential).filter(
        ProviderCredential.user_id == user_id,
        ProviderCredential.provider_id == "google_ads",
    ).first()
    if not cred or not cred.value_encrypted:
        return None
    try:
        dec = decrypt_token(cred.value_encrypted)
        data = json.loads(dec) if isinstance(dec, str) and dec.strip().startswith("{") else {}
        if isinstance(data, dict) and data.get("refresh_token"):
            return {
                "developer_token": (data.get("developer_token") or data.get("developerToken") or "").strip(),
                "client_id": (data.get("client_id") or data.get("clientId") or "").strip(),
                "client_secret": (data.get("client_secret") or data.get("clientSecret") or "").strip(),
                "refresh_token": (data.get("refresh_token") or data.get("refreshToken") or "").strip(),
                "customer_id": (data.get("customer_id") or data.get("customerId") or "").strip(),
            }
    except Exception:
        pass
    return None


def _to_inr(spend: Decimal, currency: str, usd_to_inr: Optional[Decimal] = None) -> Decimal:
    """Convert spend to INR if currency is USD. Otherwise return as-is (assume INR)."""
    if not spend or spend <= 0:
        return Decimal("0")
    currency = (currency or "INR").upper()
    if currency == "INR":
        return spend
    if currency == "USD":
        rate = usd_to_inr or DEFAULT_USD_TO_INR
        return (spend * rate).quantize(Decimal("0.01"))
    return spend


def _upsert_ad_spend(db: Session, target_date: date, platform: str, spend_inr: Decimal) -> None:
    """Insert or update ad_spend_daily row for (date, platform)."""
    row = db.query(AdSpendDaily).filter(
        AdSpendDaily.date == target_date,
        AdSpendDaily.platform == platform,
    ).first()
    now = datetime.now(timezone.utc)
    if row:
        row.spend = spend_inr
        row.currency = "INR"
        row.synced_at = now
    else:
        row = AdSpendDaily(
            date=target_date,
            platform=platform,
            spend=spend_inr,
            currency="INR",
            synced_at=now,
        )
        db.add(row)
    db.flush()


async def sync_ad_spend_for_date(db: Session, user_id: str, target_date: date) -> dict:
    """
    Fetch Meta and Google ad spend for target_date and upsert ad_spend_daily.
    Returns { "meta": spend_inr, "google": spend_inr, "errors": [] }.
    """
    result = {"meta": Decimal("0"), "google": Decimal("0"), "errors": []}
    # Meta
    meta_creds = _get_meta_credentials(db, user_id)
    if meta_creds and meta_creds.get("ad_account_id") and meta_creds.get("access_token"):
        try:
            spend, currency = await fetch_meta_spend_for_date(
                meta_creds["ad_account_id"],
                meta_creds["access_token"],
                target_date,
            )
            spend_inr = _to_inr(spend, currency)
            _upsert_ad_spend(db, target_date, "meta", spend_inr)
            result["meta"] = spend_inr
        except Exception as e:
            logger.exception("Meta ad spend sync failed: %s", e)
            result["errors"].append(f"Meta: {str(e)}")
    # Google
    google_creds = _get_google_credentials(db, user_id)
    if google_creds and google_creds.get("refresh_token"):
        try:
            spend, currency = await fetch_google_spend_for_date(
                google_creds.get("developer_token", ""),
                google_creds.get("client_id", ""),
                google_creds.get("client_secret", ""),
                google_creds.get("refresh_token", ""),
                google_creds.get("customer_id", ""),
                target_date,
            )
            spend_inr = _to_inr(spend, currency)
            _upsert_ad_spend(db, target_date, "google", spend_inr)
            result["google"] = spend_inr
        except Exception as e:
            logger.exception("Google ad spend sync failed: %s", e)
            result["errors"].append(f"Google: {str(e)}")
    return result


def get_first_user_id_for_sync(db: Session) -> Optional[str]:
    """Return first user id that has meta_ads or google_ads credentials (for nightly sync)."""
    for provider in ("meta_ads", "google_ads"):
        cred = db.query(ProviderCredential).filter(
            ProviderCredential.provider_id == provider,
            ProviderCredential.value_encrypted.isnot(None),
        ).first()
        if cred:
            return cred.user_id
    # Fallback: first user in DB
    user = db.query(User).first()
    return user.id if user else None
