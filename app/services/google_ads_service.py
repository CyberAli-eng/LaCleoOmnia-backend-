"""
Google Ads API: fetch daily ad cost for CAC.
Uses Reporting API: cost_micros, segments.date. Converts to INR if needed.
Requires: developer_token, client_id, client_secret, refresh_token (OAuth2).
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def fetch_google_spend_for_date(
    developer_token: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    customer_id: str,
    target_date: date,
) -> tuple[Decimal, str]:
    """
    Fetch cost for a single day from Google Ads Reporting API.
    Returns (spend_amount, currency). cost_micros / 1_000_000 = cost in account currency.
    """
    if not all([developer_token, client_id, client_secret, refresh_token]):
        logger.info("Google Ads: credentials not configured; returning 0")
        return Decimal("0"), "INR"
    
    try:
        # OAuth2 refresh token flow
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]
        
        # Google Ads Reporting API query
        headers = {
            "Authorization": f"Bearer {access_token}",
            "developer-token": developer_token,
            "Content-Type": "application/json",
        }
        
        query = {
            "query": f"""
            SELECT segments.date, metrics.cost_micros, account.currency_code
            WHERE segments.date = '{target_date.isoformat()}'
            """
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://googleads.googleapis.com/v17/customers/{customer_id}/googleAds:search",
                headers=headers,
                json=query
            )
            response.raise_for_status()
            
            data = response.json()
            
            if "results" in data and data["results"]:
                result = data["results"][0]
                cost_micros = result["metrics"]["costMicros"]
                currency = result["account"]["currencyCode"]
                spend = Decimal(cost_micros) / Decimal("1000000")
                
                logger.info("Google Ads: fetched spend %s %s for %s", spend, currency, target_date)
                return spend, currency
            else:
                logger.info("Google Ads: no spend data found for %s", target_date)
                return Decimal("0"), "INR"
                
    except httpx.HTTPStatusError as e:
        logger.error("Google Ads API error: %s", e.response.text)
        return Decimal("0"), "INR"
    except Exception as e:
        logger.error("Google Ads sync failed for date %s: %s", target_date, e)
        return Decimal("0"), "INR"
