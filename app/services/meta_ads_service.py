"""
Meta (Facebook) Marketing API: fetch daily ad spend for CAC.
GET https://graph.facebook.com/v18.0/act_<AD_ACCOUNT_ID>/insights?fields=spend&time_range={since,until}
Requires: ad_account_id, access_token (from ProviderCredential or env).
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

META_GRAPH_BASE = "https://graph.facebook.com"
API_VERSION = "v18.0"


async def fetch_meta_spend_for_date(
    ad_account_id: str,
    access_token: str,
    target_date: date,
) -> tuple[Decimal, str]:
    """
    Fetch spend for a single day from Meta Ads Insights.
    Returns (spend_amount, currency). Spend is in account currency (often USD); caller may convert to INR.
    """
    if not ad_account_id or not access_token:
        logger.warning("Meta Ads: missing ad_account_id or access_token")
        return Decimal("0"), "USD"
    # Strip "act_" if provided
    act_id = (ad_account_id or "").strip().replace("act_", "")
    if not act_id:
        return Decimal("0"), "USD"
    since = until = target_date.isoformat()
    url = f"{META_GRAPH_BASE}/{API_VERSION}/act_{act_id}/insights"
    params = {
        "access_token": access_token,
        "fields": "spend",
        "time_range": f'{{"since":"{since}","until":"{until}"}}',
        "limit": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning("Meta Ads API error: %s %s", e.response.status_code, e.response.text[:200])
        return Decimal("0"), "USD"
    except Exception as e:
        logger.exception("Meta Ads fetch failed: %s", e)
        return Decimal("0"), "USD"
    # Response: { "data": [ { "spend": "123.45", "date_start": "...", "date_stop": "..." } ] }
    data_list = data.get("data") if isinstance(data, dict) else []
    if not data_list:
        return Decimal("0"), "USD"
    first = data_list[0] if isinstance(data_list[0], dict) else {}
    spend_str = first.get("spend") or "0"
    try:
        spend = Decimal(str(spend_str).replace(",", ""))
    except Exception:
        spend = Decimal("0")
    # Meta returns account currency in a separate call; we don't have it here. Assume USD if not present.
    currency = (first.get("account_currency") or "USD").upper()
    return spend, currency
