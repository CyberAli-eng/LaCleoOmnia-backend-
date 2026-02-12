"""
Order Tracking Controller - Sync Shopify fulfillments with Selloship tracking
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Order, Shipment, ShipmentStatus
from app.auth import get_current_user
from app.services.shopify import ShopifyService
from app.services.selloship_service import SelloshipService
from app.http.controllers.integrations import _get_shopify_integration

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/sync-tracking")
async def sync_order_tracking(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync tracking information from Shopify fulfillments with Selloship status
    """
    try:
        # Get Shopify integration
        shopify_integration = _get_shopify_integration(db, current_user)
        if not shopify_integration:
            raise HTTPException(status_code=404, detail="Shopify not connected")
        
        # Initialize services
        shopify_service = ShopifyService(shopify_integration.channel_account)
        selloship_service = SelloshipService()
        
        # Get user's orders
        orders = db.query(Order).filter(Order.user_id == current_user.id).all()
        
        synced_count = 0
        tracking_updates = []
        
        for order in orders:
            try:
                # Get Shopify fulfillments for this order
                shopify_order = await shopify_service.get_single_order(order.channel_order_id)
                fulfillments = shopify_order.get("fulfillments", [])
                
                if fulfillments:
                    for fulfillment in fulfillments:
                        tracking_id = fulfillment.get("tracking_number")
                        if tracking_id:
                            # Check if we already have this tracking
                            existing_shipment = db.query(Shipment).filter(
                                Shipment.tracking_id == tracking_id,
                                Shipment.order_id == order.id
                            ).first()
                            
                            if not existing_shipment:
                                # Get Selloship status for this tracking
                                selloship_status = await selloship_service.get_waybill_details(tracking_id)
                                
                                # Create shipment record
                                shipment = Shipment(
                                    order_id=order.id,
                                    tracking_id=tracking_id,
                                    courier=fulfillment.get("tracking_company", "Unknown"),
                                    shopify_fulfillment_id=fulfillment.get("id"),
                                    status=selloship_status.get("status", ShipmentStatus.IN_TRANSIT),
                                    current_location=selloship_status.get("current_location"),
                                    last_synced_at=datetime.utcnow()
                                )
                                db.add(shipment)
                                synced_count += 1
                                
                                tracking_updates.append({
                                    "order_id": order.id,
                                    "channel_order_id": order.channel_order_id,
                                    "tracking_id": tracking_id,
                                    "courier": fulfillment.get("tracking_company"),
                                    "shopify_status": fulfillment.get("status"),
                                    "selloship_status": selloship_status.get("status"),
                                    "current_location": selloship_status.get("current_location")
                                })
                            else:
                                # Update existing shipment
                                selloship_status = await selloship_service.get_waybill_details(tracking_id)
                                existing_shipment.status = selloship_status.get("status", existing_shipment.status)
                                existing_shipment.current_location = selloship_status.get("current_location")
                                existing_shipment.last_synced_at = datetime.utcnow()
                                
            except Exception as e:
                logger.error(f"Failed to sync order {order.id}: {e}")
                continue
        
        db.commit()
        
        return {
            "message": f"Synced {synced_count} tracking updates",
            "synced_count": synced_count,
            "tracking_updates": tracking_updates[:10],  # Return first 10 for preview
            "total_orders": len(orders)
        }
        
    except Exception as e:
        logger.exception("Tracking sync failed")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/tracking-status")
async def get_tracking_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current tracking status for all orders
    """
    try:
        # Get user's shipments with order info
        shipments = db.query(Shipment).join(Order).filter(
            Order.user_id == current_user.id
        ).all()
        
        tracking_data = []
        for shipment in shipments:
            tracking_data.append({
                "order_id": shipment.order_id,
                "channel_order_id": shipment.order.channel_order_id if shipment.order else None,
                "tracking_id": shipment.tracking_id,
                "courier": shipment.courier,
                "shopify_fulfillment_id": shipment.shopify_fulfillment_id,
                "status": shipment.status.value if shipment.status else None,
                "current_location": shipment.current_location,
                "last_synced_at": shipment.last_synced_at.isoformat() if shipment.last_synced_at else None,
                "customer_name": shipment.order.customer_name if shipment.order else None,
                "order_total": float(shipment.order.order_total) if shipment.order else None
            })
        
        return {
            "tracking_data": tracking_data,
            "total_count": len(tracking_data)
        }
        
    except Exception as e:
        logger.exception("Failed to get tracking status")
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")
