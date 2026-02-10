"""
Shared HTTP client with timeouts and optional retries for external APIs.
Use for Selloship, Delhivery, Shopify, etc. to avoid hanging and improve resilience.
"""
import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0  # seconds


async def _sleep_backoff(attempt: int) -> None:
    if attempt <= 0:
        return
    delay = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
    await asyncio.sleep(min(delay, 10.0))


async def request_with_retry(
    method: str,
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_RETRIES,
    retry_on: tuple[int, ...] = (502, 503, 504),
    **kwargs: Any,
) -> httpx.Response:
    """
    Perform HTTP request with timeout and optional retries for server/network errors.
    Retries only on retry_on status codes and on connection errors (for GET/HEAD by default).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url, **kwargs)
            if attempt < max_retries and resp.status_code in retry_on:
                await _sleep_backoff(attempt + 1)
                continue
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            last_exc = e
            if attempt < max_retries:
                logger.warning("HTTP %s %s attempt %s failed: %s", method, url, attempt + 1, e)
                await _sleep_backoff(attempt + 1)
            else:
                raise
    if last_exc:
        raise last_exc
    return resp  # type: ignore


async def get_with_retry(
    url: str,
    *,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = DEFAULT_RETRIES,
) -> httpx.Response:
    """GET with retries on 5xx and connection errors."""
    return await request_with_retry(
        "GET", url, params=params, headers=headers, timeout=timeout, max_retries=max_retries
    )


async def post_no_retry(
    url: str,
    *,
    json: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> httpx.Response:
    """POST with no retries (non-idempotent). Uses single attempt with timeout."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=json or {}, headers=headers or {})
