"""
Shipment Sync API Endpoints

Provides endpoints for syncing shipment status and triggering fulfillment sync.
These endpoints support the new order_shipments table structure.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.http.controllers.auth import get_current_user
from app.services.shopify_fulfillment_service import (
    sync_fulfillments_for_order,
    sync_all_pending_fulfillments
)
from app.workers.selloship_status_worker import run_selloship_status_worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipments/v2", tags=["Shipments"])


@router.post("/sync/order/{order_id}")
async def sync_order_fulfillments(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync Shopify fulfillments for a specific order.
    
    This endpoint is called by the frontend when user clicks refresh on an order.
    """
    try:
        result = sync_fulfillments_for_order(order_id, str(current_user.id), db)
        
        if result["success"]:
            logger.info(f"Order {order_id} fulfillment sync: {result['message']}")
            return {
                "success": True,
                "message": result["message"],
                "synced": result["synced"],
                "updated": result["updated"]
            }
        else:
            logger.error(f"Order {order_id} fulfillment sync failed: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error syncing order {order_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.post("/sync/all")
async def sync_all_fulfillments_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync all pending fulfillments for the current user.
    
    This endpoint triggers a full sync for the current user's orders.
    """
    try:
        result = sync_all_pending_fulfillments(str(current_user.id), db)
        
        if result["success"]:
            logger.info(f"User {current_user.email} fulfillment sync: {result['message']}")
            return {
                "success": True,
                "message": result["message"],
                "total_orders": result["total_orders"],
                "synced": result["synced"],
                "updated": result["updated"]
            }
        else:
            logger.error(f"User {current_user.email} fulfillment sync failed: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error syncing all fulfillments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


@router.post("/sync/selloship")
async def sync_selloship_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger Selloship status enrichment for shipments.
    
    This endpoint manually triggers the Selloship status worker.
    """
    try:
        result = run_selloship_status_worker()
        
        if result["success"]:
            logger.info(f"Selloship status sync: {result['message']}")
            return {
                "success": True,
                "message": result["message"],
                "total_processed": result["total_processed"],
                "successful": result["successful"],
                "failed": result["failed"]
            }
        else:
            logger.error(f"Selloship status sync failed: {result['message']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error syncing Selloship status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Selloship sync failed: {str(e)}"
        )


@router.get("/status/{tracking_number}")
async def get_shipment_status(
    tracking_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed status for a specific tracking number.
    
    Returns combined Shopify and Selloship status for a tracking number.
    """
    try:
        from app.models import OrderShipment
        
        # Find shipment by tracking number
        shipment = db.query(OrderShipment).filter(
            OrderShipment.tracking_number == tracking_number
        ).first()
        
        if not shipment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tracking number {tracking_number} not found"
            )
        
        # Return comprehensive shipment information
        return {
            "success": True,
            "shipment": {
                "id": shipment.id,
                "trackingNumber": shipment.tracking_number,
                "courier": shipment.courier,
                "fulfillmentStatus": shipment.fulfillment_status,
                "deliveryStatus": shipment.delivery_status,
                "selloshipStatus": shipment.selloship_status,
                "lastSynced": shipment.last_synced_at.isoformat() if shipment.last_synced_at else None,
                "createdAt": shipment.created_at.isoformat() if shipment.created_at else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shipment status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get shipment status: {str(e)}"
        )
