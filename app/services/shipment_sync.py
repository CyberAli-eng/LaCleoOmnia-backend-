"""
Unified shipment sync: single loop over all active shipments.
Dispatches to DelhiveryService or SelloshipService by courier_name.
Uses ProviderCredential (or env) per user per courier. Status/cost updates trigger profit recompute.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings
from app.models import Shipment, ShipmentStatus, ShipmentTracking, Order, ChannelAccount

logger = logging.getLogger(__name__)


def _get_courier_api_key(db: Any, user_id: str, courier_name: str) -> Optional[str]:
    """
    Return API key for (user_id, courier). Courier normalized: delhivery | selloship.
    Uses ProviderCredential first, then env fallback.
    """
    from app.models import ProviderCredential
    from app.services.credentials import decrypt_token

    normalized = "delhivery" if courier_name and "delhivery" in courier_name.lower() else "selloship" if courier_name and "selloship" in courier_name.lower() else None
    if not normalized:
        return None
    cred = db.query(ProviderCredential).filter(
        ProviderCredential.user_id == user_id,
        ProviderCredential.provider_id == normalized,
    ).first()
    if cred and cred.value_encrypted:
        try:
            dec = decrypt_token(cred.value_encrypted)
            data = json.loads(dec) if isinstance(dec, str) and dec.strip().startswith("{") else {"apiKey": dec}
            key = data.get("apiKey") or data.get("api_key")
            if key:
                return key
        except Exception:
            pass
    if normalized == "delhivery":
        return (getattr(settings, "DELHIVERY_API_KEY", None) or "").strip() or None
    if normalized == "selloship":
        return (getattr(settings, "SELLOSHIP_API_KEY", None) or "").strip() or None
    return None


def _user_id_for_shipment(db: Any, shipment: Shipment) -> Optional[str]:
    """Resolve user_id for a shipment via order -> channel_account."""
    order = db.query(Order).filter(Order.id == shipment.order_id).first()
    if not order or not order.channel_account_id:
        return None
    acc = db.query(ChannelAccount).filter(ChannelAccount.id == order.channel_account_id).first()
    return acc.user_id if acc else None


def _get_selloship_credentials(db: Any, user_id: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (api_key, username, password) for Selloship from ProviderCredential or env."""
    from app.models import ProviderCredential
    from app.services.credentials import decrypt_token

    cred = db.query(ProviderCredential).filter(
        ProviderCredential.user_id == user_id,
        ProviderCredential.provider_id == "selloship",
    ).first()
    if cred and cred.value_encrypted:
        try:
            dec = decrypt_token(cred.value_encrypted)
            data = json.loads(dec) if isinstance(dec, str) and dec.strip().startswith("{") else {"apiKey": dec}
            api_key = data.get("apiKey") or data.get("api_key")
            username = data.get("username")
            password = data.get("password")
            if api_key or (username and password):
                return (api_key, username, password)
        except Exception:
            pass
    key = (getattr(settings, "SELLOSHIP_API_KEY", None) or "").strip() or None
    user = (getattr(settings, "SELLOSHIP_USERNAME", None) or "").strip() or None
    pwd = (getattr(settings, "SELLOSHIP_PASSWORD", None) or "").strip() or None
    return (key, user, pwd) if (key or (user and pwd)) else (None, None, None)


async def sync_shipments(db: Any, user_id: Optional[str] = None) -> dict:
    """
    Sync all active shipments. Delhivery: one get_tracking per shipment. Selloship: batch GET /waybillDetails (max 50 per call per Base.com spec).
    Returns { synced: int, errors: list }.
    """
    from app.services.delhivery_service import get_client as get_delhivery_client
    from app.services.selloship_service import get_selloship_client
    from app.services.profit_calculator import compute_profit_for_order

    final_statuses = (ShipmentStatus.DELIVERED, ShipmentStatus.RTO_DONE, ShipmentStatus.LOST)
    query = (
        db.query(Shipment)
        .filter(Shipment.status.notin_(final_statuses))
    )
    if user_id:
        query = (
            query.join(Order, Shipment.order_id == Order.id)
            .join(ChannelAccount, Order.channel_account_id == ChannelAccount.id)
            .filter(ChannelAccount.user_id == user_id)
        )
    shipments_list = query.all()
    synced = 0
    errors: list[str] = []

    # Split Delhivery vs Selloship; for Selloship group by user_id for batch
    delhivery_shipments = []
    selloship_by_user: dict[str, list] = {}
    for s in shipments_list:
        awb = (s.awb_number or "").strip()
        if not awb:
            continue
        courier_raw = (s.courier_name or "").strip().lower()
        if "delhivery" in courier_raw:
            delhivery_shipments.append(s)
        elif "selloship" in courier_raw:
            uid = user_id or _user_id_for_shipment(db, s) or ""
            selloship_by_user.setdefault(uid, []).append(s)
    # Delhivery: one-by-one
    for s in delhivery_shipments:
        awb = (s.awb_number or "").strip()
        uid = user_id or _user_id_for_shipment(db, s)
        api_key = _get_courier_api_key(db, uid or "", s.courier_name or "")
        if not api_key:
            continue
        try:
            client = get_delhivery_client(api_key)
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
            try:
                s.status = ShipmentStatus(internal_status) if internal_status in [e.value for e in ShipmentStatus] else s.status
            except (ValueError, TypeError):
                pass
            s.last_synced_at = datetime.now(timezone.utc)
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
            logger.warning("Sync shipment %s (Delhivery) failed: %s", awb, e)
            errors.append(f"{awb}: {e}")

    # Selloship: batch GET /waybillDetails (max 50 per call)
    for uid, selloship_list in selloship_by_user.items():
        api_key, username, password = _get_selloship_credentials(db, uid)
        if not api_key and not (username and password):
            continue
        client = get_selloship_client(api_key=api_key, username=username, password=password)
        awb_list = [s.awb_number.strip() for s in selloship_list]
        for i in range(0, len(awb_list), 50):
            chunk_awbs = awb_list[i : i + 50]
            chunk_shipments = [s for s in selloship_list if (s.awb_number or "").strip() in chunk_awbs]
            try:
                results = await client.get_waybill_details_batch(chunk_awbs)
            except Exception as e:
                errors.append(f"Selloship batch: {e}")
                continue
            by_awb = {r.get("waybill", "").strip(): r for r in results if r.get("waybill")}
            for s in chunk_shipments:
                awb = (s.awb_number or "").strip()
                r = by_awb.get(awb)
                if not r:
                    continue
                raw_status = r.get("raw_status") or r.get("status")
                internal_status = r.get("status")
                if r.get("error") and not internal_status:
                    errors.append(f"{awb}: {r.get('error')}")
                    continue
                try:
                    s.status = ShipmentStatus(internal_status) if internal_status in [e.value for e in ShipmentStatus] else s.status
                except (ValueError, TypeError):
                    pass
                s.last_synced_at = datetime.now(timezone.utc)
                if hasattr(client, "get_shipping_cost"):
                    cost = await client.get_shipping_cost(awb)
                    if cost:
                        s.forward_cost = cost.get("forward_cost") or s.forward_cost
                        s.reverse_cost = cost.get("reverse_cost") or s.reverse_cost
                payload = r.get("raw_response")
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
