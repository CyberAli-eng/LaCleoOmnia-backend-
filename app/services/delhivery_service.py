"""
Delhivery tracking: GET /api/v1/packages/json/?waybill=XXXX
Authorization: Token <API_KEY>
Maps raw status to internal: DELIVERED, RTO_DONE, RTO_INITIATED, IN_TRANSIT, LOST.
Persists to shipment_tracking when db is provided.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.http_client import get_with_retry
from app.models import ShipmentStatus

logger = logging.getLogger(__name__)

# Delhivery raw status strings (normalized lower) -> internal ShipmentStatus
# Delhivery API: Delivered, RTO, RTO-DEL, Undelivered, Lost, In Transit, etc.
DELHIVERY_TO_INTERNAL = {
    "delivered": ShipmentStatus.DELIVERED,
    "rto delivered": ShipmentStatus.RTO_DONE,
    "rto-del": ShipmentStatus.RTO_DONE,
    "rto_del": ShipmentStatus.RTO_DONE,
    "rto": ShipmentStatus.RTO_DONE,
    "undelivered": ShipmentStatus.RTO_INITIATED,
    "rto initiated": ShipmentStatus.RTO_INITIATED,
    "in transit": ShipmentStatus.IN_TRANSIT,
    "dispatched": ShipmentStatus.IN_TRANSIT,
    "pickup": ShipmentStatus.IN_TRANSIT,
    "pickup scheduled": ShipmentStatus.IN_TRANSIT,
    "lost": ShipmentStatus.LOST,
    "cancel": ShipmentStatus.LOST,
    "cancelled": ShipmentStatus.LOST,
}


def map_delhivery_status(raw_status: Optional[str]) -> ShipmentStatus:
    """
    Map Delhivery API status to internal ShipmentStatus.
    Never use raw strings in DB; always normalize.
    """
    if not raw_status or not isinstance(raw_status, str):
        return ShipmentStatus.CREATED
    normalized = raw_status.strip().lower()
    return DELHIVERY_TO_INTERNAL.get(normalized, ShipmentStatus.IN_TRANSIT)


def get_client(api_key: Optional[str] = None) -> "DelhiveryClient":
    """Return a client instance. Api key from env if not passed."""
    key = api_key or getattr(settings, "DELHIVERY_API_KEY", None) or ""
    base = getattr(settings, "DELHIVERY_TRACKING_BASE_URL", "https://track.delhivery.com")
    return DelhiveryClient(api_key=key, base_url=base)


class DelhiveryClient:
    """
    Delhivery tracking API client.
    GET https://track.delhivery.com/api/v1/packages/json/?waybill=XXXX
    Authorization: Token <API_KEY>
    """

    def __init__(self, api_key: str, base_url: str = "https://track.delhivery.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def get_tracking(self, waybill: str) -> dict:
        """
        Fetch tracking for waybill from Delhivery.
        Returns normalized dict: waybill, status (internal enum value), raw_status, delivery_status, rto_status, scan[], error.
        """
        if not self.api_key:
            logger.warning("Delhivery API key not set; returning stub")
            return {
                "waybill": waybill,
                "status": ShipmentStatus.CREATED.value,
                "raw_status": "not_configured",
                "delivery_status": None,
                "rto_status": None,
                "scan": [],
                "error": "DELHIVERY_API_KEY not set",
            }
        url = f"{self.base_url}/api/v1/packages/json/"
        params = {"waybill": waybill}
        headers = {"Authorization": f"Token {self.api_key}"}
        try:
            resp = await get_with_retry(url, params=params, headers=headers, timeout=15.0, max_retries=2)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("Delhivery API HTTP error waybill=%s status=%s", waybill, e.response.status_code)
            return {
                "waybill": waybill,
                "status": ShipmentStatus.CREATED.value,
                "raw_status": None,
                "delivery_status": None,
                "rto_status": None,
                "scan": [],
                "error": f"HTTP {e.response.status_code}",
            }
        except Exception as e:
            logger.warning("Delhivery API error waybill=%s: %s", waybill, e)
            return {
                "waybill": waybill,
                "status": ShipmentStatus.CREATED.value,
                "raw_status": None,
                "delivery_status": None,
                "rto_status": None,
                "scan": [],
                "error": str(e),
            }

        # Response shape: often { "ShipmentData": [ { "Shipment": { "AWB": "...", "Status": { "Status": "Delivered", ... }, "Scans": [...] } } ] }
        shipment_data = data.get("ShipmentData") or data.get("shipmentData") or []
        if not shipment_data:
            return {
                "waybill": waybill,
                "status": ShipmentStatus.CREATED.value,
                "raw_status": None,
                "delivery_status": None,
                "rto_status": None,
                "scan": [],
                "error": "No ShipmentData in response",
            }
        first = shipment_data[0] if isinstance(shipment_data[0], dict) else {}
        shipment = first.get("Shipment") or first.get("shipment") or first
        status_block = shipment.get("Status") or shipment.get("status") or {}
        raw_status = status_block.get("Status") or status_block.get("status") or shipment.get("Status") or ""
        if isinstance(raw_status, dict):
            raw_status = raw_status.get("Status") or raw_status.get("status") or ""
        scans = shipment.get("Scans") or shipment.get("scans") or []
        delivery_status = shipment.get("Delivery") or shipment.get("delivery")
        rto_status = shipment.get("RTO") or shipment.get("rto")
        internal = map_delhivery_status(str(raw_status))
        return {
            "waybill": waybill,
            "status": internal.value,
            "raw_status": str(raw_status),
            "delivery_status": str(delivery_status) if delivery_status is not None else None,
            "rto_status": str(rto_status) if rto_status is not None else None,
            "scan": scans if isinstance(scans, list) else [],
            "error": None,
            "raw_response": data,
        }

    async def track_shipment(self, waybill: str) -> dict:
        """Alias for get_tracking."""
        return await self.get_tracking(waybill)

    async def fetch_status(self, waybill: str) -> dict:
        """Alias for get_tracking."""
        return await self.get_tracking(waybill)

    def store_status(
        self,
        waybill: str,
        status: str,
        payload: Optional[dict] = None,
        db: Optional[Any] = None,
        delivery_status: Optional[str] = None,
        rto_status: Optional[str] = None,
    ) -> None:
        """
        Store shipment status. Persist to shipment_tracking when db is provided.
        Updates Shipment.status and Shipment.last_synced_at when shipment found.
        """
        logger.info("Delhivery store_status: waybill=%s status=%s", waybill, status)
        if db is None:
            return
        try:
            from app.models import Shipment, ShipmentTracking
            shipment = db.query(Shipment).filter(Shipment.awb_number == waybill).first()
            if not shipment:
                return
            # Map string to enum for shipment.status
            try:
                shipment.status = ShipmentStatus(status) if status in [e.value for e in ShipmentStatus] else shipment.status
            except ValueError:
                pass
            shipment.last_synced_at = datetime.now(timezone.utc)
            tracking = db.query(ShipmentTracking).filter(ShipmentTracking.shipment_id == shipment.id).first()
            if tracking:
                tracking.status = status
                tracking.delivery_status = delivery_status
                tracking.rto_status = rto_status
                tracking.raw_response = payload
                db.flush()
            else:
                tracking = ShipmentTracking(
                    shipment_id=shipment.id,
                    waybill=waybill,
                    status=status,
                    delivery_status=delivery_status,
                    rto_status=rto_status,
                    raw_response=payload,
                )
                db.add(tracking)
                db.flush()
            db.commit()
        except Exception as e:
            logger.warning("Failed to persist tracking: %s", e)
            if db:
                db.rollback()


async def sync_delhivery_shipments(db: Any, api_key: Optional[str] = None) -> dict:
    """
    Sync all active shipments (status not DELIVERED/RTO_DONE/LOST) from Delhivery.
    Uses api_key if provided, else global DELHIVERY_API_KEY.
    Updates Shipment.status, Shipment.last_synced_at, ShipmentTracking; triggers profit recompute.
    Returns { synced: int, updated: int, errors: list }.
    """
    from app.models import Shipment, ShipmentStatus, ShipmentTracking
    from app.services.profit_calculator import compute_profit_for_order

    final_statuses = (ShipmentStatus.DELIVERED, ShipmentStatus.RTO_DONE, ShipmentStatus.LOST)
    active = (
        db.query(Shipment)
        .filter(Shipment.status.notin_(final_statuses))
        .filter(Shipment.courier_name.ilike("%delhivery%"))
        .all()
    )
    synced = 0
    errors: list[str] = []
    client = get_client(api_key) if api_key else get_client()
    for s in active:
        awb = (s.awb_number or "").strip()
        if not awb:
            continue
        try:
            result = await client.get_tracking(awb)
            raw_status = result.get("raw_status") or result.get("status")
            internal_status = result.get("status")
            if isinstance(internal_status, ShipmentStatus):
                internal_status = internal_status.value
            delivery_status = result.get("delivery_status")
            rto_status = result.get("rto_status")
            payload = result.get("raw_response")
            if result.get("error") and not internal_status:
                errors.append(f"{awb}: {result.get('error')}")
                continue
            # Update shipment
            try:
                s.status = ShipmentStatus(internal_status) if internal_status in [e.value for e in ShipmentStatus] else s.status
            except (ValueError, TypeError):
                pass
            s.last_synced_at = datetime.now(timezone.utc)
            # Update or create ShipmentTracking
            tracking = db.query(ShipmentTracking).filter(ShipmentTracking.shipment_id == s.id).first()
            if tracking:
                tracking.status = raw_status or internal_status
                tracking.delivery_status = delivery_status
                tracking.rto_status = rto_status
                tracking.raw_response = payload
            else:
                tracking = ShipmentTracking(
                    shipment_id=s.id,
                    waybill=awb,
                    status=raw_status or internal_status,
                    delivery_status=delivery_status,
                    rto_status=rto_status,
                    raw_response=payload,
                )
                db.add(tracking)
            db.flush()
            compute_profit_for_order(db, s.order_id)
            synced += 1
        except Exception as e:
            logger.warning("Sync shipment %s failed: %s", awb, e)
            errors.append(f"{awb}: {e}")
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"commit: {e}")
    return {"synced": synced, "updated": synced, "errors": errors[:50]}
