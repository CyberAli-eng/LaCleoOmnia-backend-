"""
Google Ads API: fetch daily ad cost for CAC.
Uses Reporting API: cost_micros, segments.date. Converts to INR if needed.
Requires: developer_token, client_id, client_secret, refresh_token (OAuth2).
MVP: placeholder that returns 0 until full OAuth2 + google-ads library is wired.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

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
    MVP: returns (0, "INR") until Google Ads client is implemented.
    """
    if not all([developer_token, client_id, client_secret, refresh_token]):
        logger.debug("Google Ads: credentials not configured; returning 0")
        return Decimal("0"), "INR"
    # TODO: Implement OAuth2 refresh + Google Ads API query:
    #   SELECT segments.date, metrics.cost_micros WHERE segments.date = target_date
    #   Use google-ads package or REST reporting API.
    logger.debug("Google Ads sync not yet implemented for date %s", target_date)
    return Decimal("0"), "INR"
