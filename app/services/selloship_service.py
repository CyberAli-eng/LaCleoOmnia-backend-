"""
Selloship integration aligned with Base.com Shipper Integration spec:
- SP Authentication: POST /authToken (username/password) → token in Authorization header
- Get Shipment Status: GET /waybillDetails?waybills="AWB1,AWB2" (max 50), response: waybillDetails[].waybill, currentStatus, statusDate, current_location
Maps currentStatus (e.g. IN_TRANSIT, DELIVERED) to internal ShipmentStatus. Never store raw strings in DB.
"""
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.http_client import get_with_retry, post_no_retry
from app.models import ShipmentStatus

logger = logging.getLogger(__name__)

# Base.com Shipper Integration: currentStatus values (and common variants) → internal ShipmentStatus
SELLOSHIP_TO_INTERNAL = {
    "delivered": ShipmentStatus.DELIVERED,
    "in_transit": ShipmentStatus.IN_TRANSIT,
    "in transit": ShipmentStatus.IN_TRANSIT,
    "rto": ShipmentStatus.RTO_DONE,
    "rto_done": ShipmentStatus.RTO_DONE,
    "rto done": ShipmentStatus.RTO_DONE,
    "undelivered": ShipmentStatus.RTO_INITIATED,
    "rto_initiated": ShipmentStatus.RTO_INITIATED,
    "rto initiated": ShipmentStatus.RTO_INITIATED,
    "lost": ShipmentStatus.LOST,
    "cancelled": ShipmentStatus.RTO_DONE,
    "canceled": ShipmentStatus.RTO_DONE,
    "dispatched": ShipmentStatus.SHIPPED,
    "shipped": ShipmentStatus.SHIPPED,
    "pickup": ShipmentStatus.IN_TRANSIT,
    "out_for_delivery": ShipmentStatus.IN_TRANSIT,
    "out for delivery": ShipmentStatus.IN_TRANSIT,
}

# Uppercase/underscore form as returned by Base spec (e.g. IN_TRANSIT)
for _k, _v in list(SELLOSHIP_TO_INTERNAL.items()):
    _upper = _k.upper().replace(" ", "_")
    if _upper not in SELLOSHIP_TO_INTERNAL:
        SELLOSHIP_TO_INTERNAL[_upper] = _v


def map_selloship_status(raw_status: Optional[str]) -> ShipmentStatus:
    """Map shipper currentStatus to internal ShipmentStatus. Never use raw strings in DB."""
    if not raw_status or not isinstance(raw_status, str):
        return ShipmentStatus.CREATED
    normalized_lower = raw_status.strip().lower()
    normalized_upper = raw_status.strip().upper().replace(" ", "_")
    return (
        SELLOSHIP_TO_INTERNAL.get(normalized_lower)
        or SELLOSHIP_TO_INTERNAL.get(normalized_upper)
        or ShipmentStatus.IN_TRANSIT
    )


def build_waybill_payload_from_order(
    order: Any,
    items: list[Any],
    *,
    pickup_address: Optional[dict] = None,
    channel_code: str = "OMS",
    channel_name: str = "LaCleoOmnia",
) -> dict:
    """
    Build minimal Base.com /waybill payload from Order and OrderItems.
    order: must have id, channel_order_id, customer_name, customer_email, shipping_address, payment_mode, order_total, created_at.
    items: list of objects with sku, title, qty, price.
    """
    # Format order date per spec: dd-mmm-yyyy HH:mm:ss
    order_date = getattr(order, "created_at", None) or datetime.now(timezone.utc)
    if hasattr(order_date, "strftime"):
        order_date_str = order_date.strftime("%d-%b-%Y %H:%M:%S")
    else:
        order_date_str = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S")
    shipping = (getattr(order, "shipping_address", None) or "").strip() or "Address not provided"
    payment_mode = getattr(order, "payment_mode", None)
    pm_str = str(payment_mode).upper() if payment_mode else "PREPAID"
    if "COD" not in pm_str and "PREPAID" not in pm_str:
        pm_str = "PREPAID"
    total = float(getattr(order, "order_total", 0) or 0)
    collectable = "0" if "PREPAID" in pm_str else str(total)
    waybill_items = [
        {
            "name": getattr(it, "title", "") or getattr(it, "sku", ""),
            "description": getattr(it, "title", "") or "",
            "quantity": int(getattr(it, "qty", 1) or 1),
            "skuCode": str(getattr(it, "sku", "") or ""),
            "itemPrice": float(getattr(it, "price", 0) or 0),
            "imageURL": "",
            "hsnCode": "",
            "tags": "",
            "brand": "",
            "color": "",
            "category": "",
            "size": "",
            "item_details": "",
            "ean": "",
        }
        for it in (items or [])
    ]
    if not waybill_items:
        waybill_items = [{"name": "Order", "description": "Order", "quantity": 1, "skuCode": "ORD", "itemPrice": total, "imageURL": "", "hsnCode": "", "tags": "", "brand": "", "color": "", "category": "", "size": "", "item_details": "", "ean": ""}]
    payload = {
        "serviceType": "STANDARD",
        "returnShipmentFlag": "false",
        "Shipment": {
            "code": str(getattr(order, "id", "")),
            "orderCode": str(getattr(order, "channel_order_id", "") or ""),
            "channelCode": channel_code,
            "channelName": channel_name,
            "customField": [],
            "invoiceCode": str(getattr(order, "channel_order_id", "") or ""),
            "orderDate": order_date_str,
            "fullFilllmentTat": order_date_str,
            "weight": "1.0000",
            "length": "30",
            "height": "10",
            "breadth": "15",
            "numberOfBoxes": "1",
            "items": waybill_items,
        },
        "deliveryAddressDetails": {
            "name": str(getattr(order, "customer_name", "") or ""),
            "email": str(getattr(order, "customer_email", "") or ""),
            "phone": "0000000000",
            "address1": shipping[:200],
            "address2": "",
            "pincode": "000000",
            "city": "",
            "state": "",
            "country": "India",
            "stateCode": "",
            "countryCode": "IN",
            "latitude": 0,
            "longitude": 0,
            "gstin": "",
            "alternatePhone": "",
            "district": "",
        },
        "pickupAddressId": "",
        "returnAddressId": "",
        "currencyCode": "INR",
        "paymentMode": pm_str,
        "totalAmount": str(total),
        "collectableAmount": collectable,
        "courierName": "Selloship",
        "customField": [],
    }
    if pickup_address and isinstance(pickup_address, dict):
        payload["pickupAddressDetails"] = pickup_address
    return payload


async def fetch_selloship_token(
    username: str,
    password: str,
    auth_url: Optional[str] = None,
) -> Optional[str]:
    """
    Call Selloship auth API (e.g. selloship.com/api/lock_actvs/channels/authToken).
    Returns the token string on SUCCESS, None otherwise. Used to validate credentials on connect.
    """
    url = (auth_url or getattr(settings, "SELLOSHIP_AUTH_URL", None) or "https://selloship.com/api/lock_actvs/channels/authToken").strip()
    if not username or not password:
        return None
    payload = {"username": username.strip(), "password": password}
    headers = {"Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Selloship fetch_selloship_token failed: %s", e)
        return None
    if isinstance(data, dict) and (data.get("status") or "").upper() == "SUCCESS":
        token = data.get("token")
        if token:
            return token
    return None


def get_selloship_client(
    api_key: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    auth_url: Optional[str] = None,
) -> "SelloshipService":
    """
    Return a Selloship client. Uses Base.com Shipper Integration flow.
    - If username + password: POST to auth_url (or SELLOSHIP_AUTH_URL) to get token, then use Bearer.
    - Else use api_key (or SELLOSHIP_API_KEY) as Bearer token.
    """
    key = (api_key or getattr(settings, "SELLOSHIP_API_KEY", None) or "").strip() or None
    user = (username or getattr(settings, "SELLOSHIP_USERNAME", None) or "").strip() or None
    pwd = (password or getattr(settings, "SELLOSHIP_PASSWORD", None) or "").strip() or None
    base = getattr(settings, "SELLOSHIP_API_BASE_URL", "https://api.selloship.com")
    url = (auth_url or getattr(settings, "SELLOSHIP_AUTH_URL", None) or "").strip() or None
    return SelloshipService(api_key=key or "", base_url=base, username=user, password=pwd, auth_url=url)


class SelloshipService:
    """
    Selloship API client aligned with Base.com Shipper Integration for Base.com.
    - Auth: POST /authToken with username/password; use token in Authorization header.
    - Get Shipment Status: GET /waybillDetails with waybills="AWB1,AWB2" (max 50 per call).
    """

    # Token cache: (token_string, expires_at)
    _token_cache: Optional[tuple[str, float]] = None
    TOKEN_CACHE_TTL_SEC = 3000  # ~50 min

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.selloship.com",
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_url: Optional[str] = None,
    ):
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.username = (username or "").strip() or None
        self.password = (password or "").strip() or None
        self.auth_url = (auth_url or "").strip() or None

    def _has_token_auth(self) -> bool:
        return bool(self.username and self.password)

    async def _get_auth_token(self) -> Optional[str]:
        """POST to auth URL (or base_url/authToken) with username/password. Returns token or None."""
        if not self._has_token_auth():
            return None
        url = self.auth_url or f"{self.base_url}/authToken"
        payload = {"username": self.username, "password": self.password}
        headers = {"Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("Selloship authToken failed: %s", e)
            return None
        if isinstance(data, dict) and (data.get("status") or "").upper() == "SUCCESS":
            token = data.get("token")
            if token:
                return token
        return None

    async def _get_headers(self) -> dict:
        """Authorization header: Bearer token from /authToken or api_key. Content-Type application/json."""
        headers = {"Content-Type": "application/json"}
        if self._has_token_auth():
            now = time.time()
            if SelloshipService._token_cache is not None:
                tok, exp = SelloshipService._token_cache
                if exp > now:
                    headers["Authorization"] = f"Bearer {tok}"
                    return headers
            token = await self._get_auth_token()
            if token:
                SelloshipService._token_cache = (token, now + self.TOKEN_CACHE_TTL_SEC)
                headers["Authorization"] = f"Bearer {token}"
            return headers
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_waybill_detail(self, detail: dict, awb_fallback: str) -> dict:
        """
        Parse one entry from waybillDetails[] per Base.com spec:
        waybill, currentStatus, statusDate, current_location
        """
        waybill = (detail.get("waybill") or awb_fallback or "").strip()
        current_status = detail.get("currentStatus") or detail.get("current_status") or ""
        status_date = detail.get("statusDate") or detail.get("status_date")
        current_location = detail.get("current_location") or detail.get("currentLocation")
        internal = map_selloship_status(current_status)
        return {
            "waybill": waybill,
            "status": internal.value,
            "raw_status": current_status,
            "status_date": status_date,
            "current_location": current_location,
            "delivery_status": None,
            "rto_status": None,
            "scan": [],
            "error": None,
            "raw_response": detail,
        }

    async def get_waybill_details_batch(self, awb_list: list[str]) -> list[dict]:
        """
        GET /waybillDetails with waybills="AWB1,AWB2,..." (max 50 per Base.com spec).
        Returns list of normalized dicts (one per waybill): waybill, status, raw_status, status_date, current_location, error.
        """
        if not awb_list:
            return []
        awb_list = [str(a).strip() for a in awb_list if str(a).strip()][:50]
        if not awb_list:
            return []
        if not self.api_key and not self._has_token_auth():
            return [
                {
                    "waybill": awb,
                    "status": ShipmentStatus.CREATED.value,
                    "raw_status": "not_configured",
                    "status_date": None,
                    "current_location": None,
                    "delivery_status": None,
                    "rto_status": None,
                    "scan": [],
                    "error": "Selloship credentials not set",
                    "raw_response": None,
                }
                for awb in awb_list
            ]
        # Query param: waybills= comma-separated; spec says "in quotes" - some APIs want literal quotes in value
        waybills_value = ",".join(awb_list)
        url = f"{self.base_url}/waybillDetails"
        params = {"waybills": waybills_value}
        headers = await self._get_headers()
        try:
            resp = await get_with_retry(url, params=params, headers=headers, timeout=20.0, max_retries=2)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Selloship waybillDetails HTTP error status=%s", e.response.status_code)
            return [
                {
                    "waybill": awb,
                    "status": ShipmentStatus.CREATED.value,
                    "raw_status": None,
                    "status_date": None,
                    "current_location": None,
                    "delivery_status": None,
                    "rto_status": None,
                    "scan": [],
                    "error": f"HTTP {e.response.status_code}",
                    "raw_response": None,
                }
                for awb in awb_list
            ]
        except Exception as e:
            logger.warning("Selloship waybillDetails error: %s", e)
            return [
                {
                    "waybill": awb,
                    "status": ShipmentStatus.CREATED.value,
                    "raw_status": None,
                    "status_date": None,
                    "current_location": None,
                    "delivery_status": None,
                    "rto_status": None,
                    "scan": [],
                    "error": str(e),
                    "raw_response": None,
                }
                for awb in awb_list
            ]
        # Response: Status, waybillDetails[]
        if not isinstance(data, dict):
            return [
                self._parse_waybill_detail({}, awb) | {"error": "Invalid response"}
                for awb in awb_list
            ]
        if (data.get("Status") or data.get("status") or "").upper() != "SUCCESS":
            err = data.get("message") or data.get("reason") or "API returned non-SUCCESS"
            return [
                {
                    "waybill": awb,
                    "status": ShipmentStatus.CREATED.value,
                    "raw_status": None,
                    "status_date": None,
                    "current_location": None,
                    "delivery_status": None,
                    "rto_status": None,
                    "scan": [],
                    "error": err,
                    "raw_response": data,
                }
                for awb in awb_list
            ]
        details = data.get("waybillDetails") or data.get("waybill_details") or []
        if not isinstance(details, list):
            details = []
        by_awb = {}
        for d in details:
            if isinstance(d, dict):
                wb = (d.get("waybill") or "").strip()
                if wb:
                    by_awb[wb] = self._parse_waybill_detail(d, wb)
        result = []
        for awb in awb_list:
            if awb in by_awb:
                result.append(by_awb[awb])
            else:
                result.append(
                    {
                        "waybill": awb,
                        "status": ShipmentStatus.CREATED.value,
                        "raw_status": None,
                        "status_date": None,
                        "current_location": None,
                        "delivery_status": None,
                        "rto_status": None,
                        "scan": [],
                        "error": "Not in response",
                        "raw_response": None,
                    }
                )
        return result

    async def get_tracking(self, awb: str) -> dict:
        """
        Fetch tracking for one waybill via GET /waybillDetails (Base.com spec).
        Returns normalized dict: waybill, status, raw_status, status_date, current_location, scan[], error.
        """
        results = await self.get_waybill_details_batch([awb])
        if not results:
            return {
                "waybill": awb,
                "status": ShipmentStatus.CREATED.value,
                "raw_status": None,
                "delivery_status": None,
                "rto_status": None,
                "scan": [],
                "error": "No response",
                "raw_response": None,
            }
        return results[0]

    async def get_shipping_cost(self, awb: str) -> Optional[dict]:
        """
        Fetch shipping cost for waybill if exposed in waybillDetails response.
        Returns { "forward_cost": Decimal, "reverse_cost": Decimal } or None.
        """
        if not self.api_key and not self._has_token_auth():
            return None
        result = await self.get_tracking(awb)
        if result.get("error"):
            return None
        raw = result.get("raw_response") or {}
        if not isinstance(raw, dict):
            return None
        forward = raw.get("forward_cost") or raw.get("shipping_cost") or raw.get("cost")
        reverse = raw.get("reverse_cost") or raw.get("rto_cost") or 0
        try:
            fwd = Decimal(str(forward)) if forward is not None else Decimal("0")
            rev = Decimal(str(reverse)) if reverse is not None else Decimal("0")
            return {"forward_cost": fwd, "reverse_cost": rev}
        except Exception:
            return None

    async def get_costs(self, awb: str) -> Optional[dict]:
        """Alias for get_shipping_cost."""
        return await self.get_shipping_cost(awb)

    async def create_waybill(self, payload: dict) -> dict:
        """
        POST /waybill per Base.com spec. Payload: serviceType, returnShipmentFlag, Shipment, deliveryAddressDetails,
        pickupAddressDetails, returnAddressDetails, currencyCode, paymentMode, totalAmount, collectableAmount, etc.
        Returns { "status": "SUCCESS", "waybill": str, "shippingLabel": str (PDF URL), "courierName": str, "routingCode": str }
        or { "status": "FAILED", "message": str, "reason": str }.
        """
        if not self.api_key and not self._has_token_auth():
            return {"status": "FAILED", "message": "Selloship credentials not set", "reason": "NOT_CONFIGURED"}
        url = f"{self.base_url}/waybill"
        headers = await self._get_headers()
        try:
            resp = await post_no_retry(url, json=payload, headers=headers, timeout=30.0)
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning("Selloship create_waybill error: %s", e)
            return {"status": "FAILED", "message": str(e), "reason": "REQUEST_ERROR"}
        if not isinstance(data, dict):
            return {"status": "FAILED", "message": "Invalid response", "reason": "INVALID_RESPONSE"}
        if (data.get("status") or data.get("Status") or "").upper() != "SUCCESS":
            return {
                "status": "FAILED",
                "message": data.get("message") or data.get("reason") or "Waybill creation failed",
                "reason": data.get("reason") or "API_ERROR",
            }
        return {
            "status": "SUCCESS",
            "waybill": (data.get("waybill") or "").strip(),
            "shippingLabel": data.get("shippingLabel") or data.get("shipping_label"),
            "courierName": data.get("courierName") or data.get("courier_name") or "Selloship",
            "routingCode": data.get("routingCode") or data.get("routing_code"),
        }

    async def cancel_waybill(self, waybill: str) -> dict:
        """POST /cancel per Base.com spec. Returns status, waybill, errorMessage."""
        if not self.api_key and not self._has_token_auth():
            return {"status": "FAILED", "waybill": waybill, "errorMessage": "Selloship credentials not set"}
        url = f"{self.base_url}/cancel"
        headers = await self._get_headers()
        try:
            resp = await post_no_retry(url, json={"waybill": waybill.strip()}, headers=headers, timeout=15.0)
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning("Selloship cancel_waybill error: %s", e)
            return {"status": "FAILED", "waybill": waybill, "errorMessage": str(e)}
        if not isinstance(data, dict):
            return {"status": "FAILED", "waybill": waybill, "errorMessage": "Invalid response"}
        return {
            "status": (data.get("status") or data.get("Status") or "FAILED").upper(),
            "waybill": data.get("waybill") or waybill,
            "errorMessage": data.get("errorMessage") or data.get("message") or data.get("reason"),
        }

    async def generate_manifest(self, awb_numbers: list[str]) -> dict:
        """POST /manifest per Base.com spec. Returns status, manifestNumber, manifestDownloadUrl (PDF)."""
        if not self.api_key and not self._has_token_auth():
            return {"status": "FAILED", "message": "Selloship credentials not set"}
        url = f"{self.base_url}/manifest"
        headers = await self._get_headers()
        awb_list = [str(a).strip() for a in awb_numbers if str(a).strip()]
        try:
            resp = await post_no_retry(url, json={"awbNumbers": awb_list}, headers=headers, timeout=30.0)
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning("Selloship generate_manifest error: %s", e)
            return {"status": "FAILED", "message": str(e)}
        if not isinstance(data, dict) or (data.get("status") or data.get("Status") or "").upper() != "SUCCESS":
            return {
                "status": "FAILED",
                "message": data.get("message") or data.get("reason") or "Manifest generation failed",
            }
        return {
            "status": "SUCCESS",
            "manifestNumber": data.get("manifestNumber") or data.get("manifest_number"),
            "manifestDownloadUrl": data.get("manifestDownloadUrl") or data.get("manifest_download_url"),
        }

    async def update_waybill(self, payload: dict) -> dict:
        """POST /waybill/update per Base.com spec. Payload: Shipment (waybill, code, weight, etc.), source."""
        if not self.api_key and not self._has_token_auth():
            return {"status": "FAILED", "message": "Selloship credentials not set"}
        url = f"{self.base_url}/waybill/update"
        headers = await self._get_headers()
        try:
            resp = await post_no_retry(url, json=payload, headers=headers, timeout=20.0)
            data = resp.json() if resp.content else {}
        except Exception as e:
            logger.warning("Selloship update_waybill error: %s", e)
            return {"status": "FAILED", "message": str(e)}
        if not isinstance(data, dict) or (data.get("status") or data.get("Status") or "").upper() != "SUCCESS":
            return {"status": "FAILED", "message": data.get("message") or data.get("reason") or "Update failed"}
        return {
            "status": "SUCCESS",
            "waybill": data.get("waybill"),
            "shippingLabel": data.get("shippingLabel") or data.get("shipping_label"),
            "courierName": data.get("courierName") or data.get("courier_name"),
        }


async def sync_selloship_shipments(db: Any, api_key: Optional[str] = None) -> dict:
    """
    Sync all active Selloship shipments. Uses batch GET /waybillDetails (max 50 per call).
    Updates Shipment.status, Shipment.last_synced_at, ShipmentTracking; triggers profit recompute.
    Returns { synced: int, updated: int, errors: list }.
    """
    from app.models import Shipment, ShipmentStatus, ShipmentTracking
    from app.services.profit_calculator import compute_profit_for_order

    final_statuses = (ShipmentStatus.DELIVERED, ShipmentStatus.RTO_DONE, ShipmentStatus.LOST)
    active = (
        db.query(Shipment)
        .filter(Shipment.status.notin_(final_statuses))
        .filter(Shipment.courier_name.ilike("%selloship%"))
        .all()
    )
    synced = 0
    errors: list[str] = []
    client = get_selloship_client(api_key=api_key)
    awb_list = [(s.awb_number or "").strip() for s in active if (s.awb_number or "").strip()]
    if not awb_list:
        return {"synced": 0, "updated": 0, "errors": []}
    # Batch in chunks of 50 (Base.com spec max)
    chunk_size = 50
    for i in range(0, len(awb_list), chunk_size):
        chunk = awb_list[i : i + chunk_size]
        try:
            results = await client.get_waybill_details_batch(chunk)
        except Exception as e:
            errors.append(f"batch: {e}")
            continue
        shipment_by_awb = {s.awb_number.strip(): s for s in active if (s.awb_number or "").strip()}
        for r in results:
            awb = (r.get("waybill") or "").strip()
            s = shipment_by_awb.get(awb)
            if not s:
                continue
            if r.get("error") and not r.get("status"):
                errors.append(f"{awb}: {r.get('error')}")
                continue
            raw_status = r.get("raw_status") or r.get("status")
            internal_status = r.get("status")
            try:
                s.status = (
                    ShipmentStatus(internal_status)
                    if internal_status in [e.value for e in ShipmentStatus]
                    else s.status
                )
            except (ValueError, TypeError):
                pass
            s.last_synced_at = datetime.now(timezone.utc)
            cost = await client.get_shipping_cost(awb)
            if cost:
                s.forward_cost = cost.get("forward_cost") or s.forward_cost
                s.reverse_cost = cost.get("reverse_cost") or s.reverse_cost
            payload = r.get("raw_response")
            current_location = r.get("current_location")
            if payload is not None and current_location is not None:
                payload = dict(payload) if isinstance(payload, dict) else {}
                payload["current_location"] = current_location
            tracking = db.query(ShipmentTracking).filter(ShipmentTracking.shipment_id == s.id).first()
            if tracking:
                tracking.status = raw_status or internal_status
                tracking.delivery_status = r.get("delivery_status")
                tracking.rto_status = r.get("rto_status")
                tracking.raw_response = payload
            else:
                tracking = ShipmentTracking(
                    shipment_id=s.id,
                    waybill=awb,
                    status=raw_status or internal_status,
                    delivery_status=r.get("delivery_status"),
                    rto_status=r.get("rto_status"),
                    raw_response=payload,
                )
                db.add(tracking)
            db.flush()
            compute_profit_for_order(db, s.order_id)
            synced += 1
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"commit: {e}")
    return {"synced": synced, "updated": synced, "errors": errors[:50]}
