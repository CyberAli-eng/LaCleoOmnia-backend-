"""
Shipment routes: list, get by id or order_id, create, sync, generate label (Selloship).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Shipment, Order, OrderItem, User, ChannelAccount, ShipmentStatus
from app.auth import get_current_user
from app.services.shipment_sync import sync_shipments, _get_selloship_credentials
from app.services.selloship_service import get_selloship_client, build_waybill_payload_from_order

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_channel_account_ids(db: Session, user: User) -> list[str]:
    return [ca.id for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == user.id).all()]


class ShipmentCreate(BaseModel):
    order_id: str
    awb_number: str
    courier_name: str = "delhivery"
    tracking_url: str | None = None
    label_url: str | None = None
    forward_cost: float = 0.0
    reverse_cost: float = 0.0


class GenerateLabelRequest(BaseModel):
    order_id: str
    courier_name: str = "selloship"


@router.get("")
async def list_shipments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List shipments for current user's orders."""
    account_ids = _user_channel_account_ids(db, current_user)
    if not account_ids:
        return {"shipments": []}
    query = (
        db.query(Shipment)
        .join(Order, Shipment.order_id == Order.id)
        .filter(Order.channel_account_id.in_(account_ids))
        .order_by(Shipment.created_at.desc())
    )
    shipments = query.all()
    return {
        "shipments": [
            {
                "id": s.id,
                "orderId": s.order_id,
                "courierName": s.courier_name,
                "awbNumber": s.awb_number,
                "trackingUrl": s.tracking_url,
                "labelUrl": s.label_url,
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "forwardCost": float(s.forward_cost or 0),
                "reverseCost": float(s.reverse_cost or 0),
                "shippedAt": s.shipped_at.isoformat() if s.shipped_at else None,
                "lastSyncedAt": s.last_synced_at.isoformat() if s.last_synced_at else None,
                "createdAt": s.created_at.isoformat() if s.created_at else None,
            }
            for s in shipments
        ]
    }


@router.get("/order/{order_id}")
async def get_shipment_by_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get shipment for an order. 404 if not found or not user's order."""
    account_ids = _user_channel_account_ids(db, current_user)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.channel_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Order not found")
    shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return _shipment_response(shipment)


def _shipment_response(s: Shipment) -> dict:
    return {
        "shipment": {
            "id": s.id,
            "orderId": s.order_id,
            "courierName": s.courier_name,
            "awbNumber": s.awb_number,
            "trackingUrl": s.tracking_url,
            "labelUrl": s.label_url,
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "forwardCost": float(s.forward_cost or 0),
            "reverseCost": float(s.reverse_cost or 0),
            "shippedAt": s.shipped_at.isoformat() if s.shipped_at else None,
            "lastSyncedAt": s.last_synced_at.isoformat() if s.last_synced_at else None,
            "createdAt": s.created_at.isoformat() if s.created_at else None,
        }
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_shipment(
    body: ShipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a shipment for an order (link AWB). Order must belong to current user."""
    account_ids = _user_channel_account_ids(db, current_user)
    order = db.query(Order).filter(Order.id == body.order_id).first()
    if not order or order.channel_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Order not found")
    existing = db.query(Shipment).filter(Shipment.order_id == body.order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order already has a shipment")
    from decimal import Decimal
    shipment = Shipment(
        order_id=body.order_id,
        courier_name=body.courier_name or "delhivery",
        awb_number=body.awb_number.strip(),
        tracking_url=body.tracking_url,
        label_url=body.label_url,
        forward_cost=Decimal(str(body.forward_cost)),
        reverse_cost=Decimal(str(body.reverse_cost)),
        status=ShipmentStatus.CREATED,
    )
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    from app.services.profit_calculator import compute_profit_for_order
    compute_profit_for_order(db, body.order_id)
    return _shipment_response(shipment)


@router.post("/generate-label")
async def generate_label(
    body: GenerateLabelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate shipping label via Selloship (Base.com waybill). Returns waybill and label URL for use in create shipment."""
    if (body.courier_name or "").strip().lower() != "selloship":
        raise HTTPException(status_code=400, detail="Only Selloship is supported for label generation")
    account_ids = _user_channel_account_ids(db, current_user)
    order = db.query(Order).filter(Order.id == body.order_id).first()
    if not order or order.channel_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Order not found")
    existing = db.query(Shipment).filter(Shipment.order_id == body.order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Order already has a shipment")
    items = db.query(OrderItem).filter(OrderItem.order_id == body.order_id).all()
    api_key, username, password = _get_selloship_credentials(db, str(current_user.id))
    if not api_key and not (username and password):
        raise HTTPException(
            status_code=400,
            detail="Selloship not connected. Connect in Integrations → Logistics → Selloship.",
        )
    client = get_selloship_client(api_key=api_key, username=username, password=password)
    payload = build_waybill_payload_from_order(order, items)
    result = await client.create_waybill(payload)
    if (result.get("status") or "").upper() != "SUCCESS":
        msg = result.get("message") or result.get("reason") or "Label generation failed"
        raise HTTPException(status_code=400, detail=msg)
    return {
        "waybill": result.get("waybill") or "",
        "shippingLabel": result.get("shippingLabel") or "",
        "courierName": result.get("courierName") or "Selloship",
        "routingCode": result.get("routingCode"),
    }


@router.post("/sync")
async def sync_shipments_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync all active shipments (Delhivery + Selloship) for current user. Uses user API keys or env fallback."""
    result = await sync_shipments(db, user_id=current_user.id)
    return {
        "message": f"Synced {result['synced']} shipments",
        "synced": result["synced"],
        "errors": result.get("errors", [])[:20],
    }


@router.get("/{shipment_id}")
async def get_shipment(
    shipment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get shipment by id. 404 if not found or not user's order."""
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    account_ids = _user_channel_account_ids(db, current_user)
    order = db.query(Order).filter(Order.id == shipment.order_id).first()
    if not order or order.channel_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return _shipment_response(shipment)
