"""
Shipment routes: list, get by id or order_id, create, sync, generate label (Selloship).
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Shipment, Order, OrderItem, User, ChannelAccount, ShipmentStatus, OrderShipment
from app.auth import get_current_user
from app.services.shipment_sync import sync_shipments, _get_selloship_credentials
from app.services.selloship_service import get_selloship_client, build_waybill_payload_from_order
from app.services.shopify_fulfillment_sync import sync_order_fulfillments
from app.services.selloship_status_enrichment import enrich_shipment_status_by_order

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_channel_account_ids(db: Session, user: User) -> list[str]:
    return [ca.id for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == user.id).all()]


class ShipmentCreate(BaseModel):
    order_id: str
    awb_number: str
    courier_name: str = "delhivery"
    tracking_url: Optional[str] = None
    label_url: Optional[str] = None
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
    request: Request,
    shipment_id: Optional[str] = None,
    order_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync all active shipments (Delhivery + Selloship) for current user. Uses user API keys or env fallback."""
    if order_id:
        # Sync specific order's shipment
        account_ids = _user_channel_account_ids(db, current_user)
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order or (order.channel_account_id not in account_ids):
            raise HTTPException(status_code=404, detail="Order not found")
        
        shipment = db.query(Shipment).filter(Shipment.order_id == order_id).first()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")
        
        # Sync single shipment
        courier_raw = (shipment.courier_name or "").strip().lower()
        if "selloship" in courier_raw:
            from app.services.selloship_service import get_selloship_client
            api_key, username, password = _get_selloship_credentials(db, str(current_user.id))
            if not api_key and not (username and password):
                raise HTTPException(status_code=400, detail="Selloship not connected")
            client = get_selloship_client(api_key=api_key, username=username, password=password)
            try:
                result = await client.get_tracking(shipment.awb_number or "")
                # Update shipment with new status
                if not result.get("error"):
                    raw_status = result.get("raw_status") or result.get("status")
                    internal_status = result.get("status")
                    if isinstance(internal_status, ShipmentStatus):
                        shipment.status = internal_status
                    shipment.last_synced_at = datetime.now(timezone.utc)
                    db.flush()
                    # Trigger profit recompute
                    from app.services.profit_calculator import compute_profit_for_order
                    compute_profit_for_order(db, order_id)
                    db.commit()
                return {
                    "message": f"Shipment {shipment.awb_number} synced successfully",
                    "awb": shipment.awb_number,
                    "status": raw_status,
                    "last_sync": shipment.last_synced_at.isoformat() if shipment.last_synced_at else None,
                }
            except Exception as e:
                logger.warning("Failed to sync Selloship shipment %s: %s", shipment.awb_number, e)
                raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
        else:
            # Fallback to full sync for other couriers
            result = await sync_shipments(db, user_id=current_user.id)
            return result
    else:
        # Full sync for all shipments
        result = await sync_shipments(db, user_id=current_user.id)
        
        # Check if AWB discovery should be triggered
        sync_awb_discovery = request.query_params.get("sync_awb_discovery", "false").lower() == "true"
        if sync_awb_discovery:
            from app.services.selloship_service import process_awb_discovery_batch
            processed, found = await process_awb_discovery_batch(db, batch_size=50)
            return {
                "message": f"Synced {result['synced']} shipments and processed {processed} orders for AWB discovery",
                "shipments_synced": result["synced"],
                "orders_processed": processed,
                "awbs_found": found,
                "errors": result.get("errors", [])[:20],
            }
        
        return {
            "message": f"Synced {result['synced']} shipments",
            "synced": result["synced"],
            "errors": result.get("errors", [])[:20],
        }


@router.get("/debug/selloship/awb")
async def debug_selloship_awb_test(
    awb: str = "SLSC1002159720",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Test endpoint to verify Selloship AWB API connectivity.
    """
    try:
        from app.services.selloship_service import get_selloship_client
        
        # Get Selloship credentials
        api_key, username, password = _get_selloship_credentials(db, str(current_user.id))
        if not api_key and not (username and password):
            return {"status": "error", "message": "Selloship not connected"}
        
        client = get_selloship_client(api_key=api_key, username=username, password=password)
        result = await client.get_tracking(awb)
        
        return {
            "status": "success",
            "awb": awb,
            "result": result,
            "message": "Selloship API test completed"
        }
        
    except Exception as e:
        logger.error(f"[DEBUG] Selloship AWB test failed: {e}")
        return {
            "status": "error",
            "message": f"API test failed: {str(e)}"
        }


@router.get("/debug/selloship")
async def debug_selloship_awb_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Debug endpoint for Selloship AWB sync status.
    Returns statistics for monitoring and troubleshooting.
    """
    try:
        from app.services.awb_sync_worker import get_awb_sync_stats
        
        stats = await get_awb_sync_stats(db)
        
        return {
            "status": "success",
            "data": stats,
            "message": "Selloship AWB sync debug information"
        }
        
    except Exception as e:
        logger.error(f"[DEBUG] Failed to get Selloship debug info: {e}")
        raise HTTPException(status_code=500, detail=f"Debug endpoint failed: {str(e)}")


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


# ===== SHOPIFY-CENTRIC SHIPMENT ENDPOINTS =====

@router.get("/v2/order/{order_id}")
async def get_order_shipments(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get Shopify-centric shipments for an order."""
    account_ids = _user_channel_account_ids(db, current_user)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.channel_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Order not found")
    
    shipments = db.query(OrderShipment).filter(OrderShipment.order_id == order_id).all()
    
    return {
        "shipments": [
            {
                "id": s.id,
                "orderId": s.order_id,
                "shopifyFulfillmentId": s.shopify_fulfillment_id,
                "trackingNumber": s.tracking_number,
                "courier": s.courier,
                "fulfillmentStatus": s.fulfillment_status,
                "deliveryStatus": s.delivery_status,
                "selloshipStatus": s.selloship_status,
                "lastSyncedAt": s.last_synced_at.isoformat() if s.last_synced_at else None,
                "createdAt": s.created_at.isoformat() if s.created_at else None,
                "updatedAt": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in shipments
        ]
    }


@router.post("/v2/sync/order/{order_id}")
async def sync_order_shipments(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync Shopify fulfillments and enrich Selloship status for an order."""
    account_ids = _user_channel_account_ids(db, current_user)
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order or order.channel_account_id not in account_ids:
        raise HTTPException(status_code=404, detail="Order not found")
    
    try:
        # Step 1: Sync Shopify fulfillments
        shopify_result = await sync_order_fulfillments(db, order_id)
        
        # Step 2: Enrich Selloship status
        selloship_result = await enrich_shipment_status_by_order(db, order_id)
        
        return {
            "status": "SUCCESS",
            "message": "Order shipments synced successfully",
            "shopify_sync": shopify_result,
            "selloship_sync": selloship_result
        }
        
    except Exception as e:
        logger.error(f"Failed to sync shipments for order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/v2/sync/fulfillments")
async def sync_all_fulfillments(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync Shopify fulfillments for all orders without shipments."""
    try:
        from app.services.shopify_fulfillment_sync import sync_all_pending_fulfillments
        
        result = await sync_all_pending_fulfillments(db, limit=limit)
        
        return {
            "status": "SUCCESS",
            "message": "Fulfillments sync completed",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Failed to sync fulfillments: {e}")
        raise HTTPException(status_code=500, detail=f"Fulfillment sync failed: {str(e)}")


@router.post("/v2/sync/status")
async def sync_shipment_status(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync Selloship status enrichment for active shipments."""
    try:
        from app.services.selloship_status_enrichment import enrich_all_active_shipments
        
        result = await enrich_all_active_shipments(db, limit=limit)
        
        return {
            "status": "SUCCESS",
            "message": "Status enrichment completed",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Failed to sync shipment status: {e}")
        raise HTTPException(status_code=500, detail=f"Status sync failed: {str(e)}")


@router.get("/v2/stats")
async def get_shipment_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get shipment statistics for dashboard."""
    try:
        account_ids = _user_channel_account_ids(db, current_user)
        
        # Get orders for current user
        orders = db.query(Order).filter(Order.channel_account_id.in_(account_ids)).all()
        order_ids = [o.id for o in orders]
        
        if not order_ids:
            return {
                "totalOrders": 0,
                "ordersWithShipments": 0,
                "totalShipments": 0,
                "shipmentsWithTracking": 0,
                "deliveredCount": 0,
                "inTransitCount": 0,
                "pendingCount": 0,
                "rtoCount": 0
            }
        
        # Get shipment stats
        total_orders = len(order_ids)
        orders_with_shipments = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids)
        ).distinct(OrderShipment.order_id).count()
        
        total_shipments = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids)
        ).count()
        
        shipments_with_tracking = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids),
            OrderShipment.tracking_number.isnot(None)
        ).count()
        
        delivered_count = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids),
            OrderShipment.delivery_status == 'DELIVERED'
        ).count()
        
        in_transit_count = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids),
            OrderShipment.delivery_status == 'IN_TRANSIT'
        ).count()
        
        pending_count = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids),
            OrderShipment.delivery_status == 'PENDING'
        ).count()
        
        rto_count = db.query(OrderShipment).filter(
            OrderShipment.order_id.in_(order_ids),
            OrderShipment.delivery_status.in_(['RTO', 'RTO_INITIATED', 'RTO_DONE'])
        ).count()
        
        return {
            "totalOrders": total_orders,
            "ordersWithShipments": orders_with_shipments,
            "totalShipments": total_shipments,
            "shipmentsWithTracking": shipments_with_tracking,
            "deliveredCount": delivered_count,
            "inTransitCount": in_transit_count,
            "pendingCount": pending_count,
            "rtoCount": rto_count
        }
        
    except Exception as e:
        logger.error(f"Failed to get shipment stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
