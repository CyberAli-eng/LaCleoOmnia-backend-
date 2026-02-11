"""
Dynamic Sync API Controllers
Provides endpoints for dynamic Shopify and shipment synchronization
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.services.dynamic_shopify_sync import (
    sync_shopify_dynamically, 
    sync_shipment_status_dynamically,
    DynamicShopifySync
)
from typing import Dict, Any
import asyncio

router = APIRouter(prefix="/sync", tags=["dynamic-sync"])

@router.post("/shopify")
async def sync_shopify_endpoint(
    limit: int = 250,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Sync ALL orders from Shopify (fulfilled and unfulfilled)
    Creates shipment records with tracking numbers from fulfillments
    """
    try:
        result = await sync_shopify_dynamically(db, limit=limit)
        
        if result.get("status") == "FAILED":
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        return {
            "success": True,
            "message": "Shopify sync completed successfully",
            "data": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shopify sync failed: {str(e)}")

@router.post("/shipments")
async def sync_shipments_endpoint(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Sync shipment status from couriers (Selloship, etc.)
    Updates existing shipment records with latest status
    """
    try:
        result = await sync_shipment_status_dynamically(db, limit=limit)
        
        if result.get("status") == "FAILED":
            raise HTTPException(status_code=500, detail=result.get("error"))
        
        return {
            "success": True,
            "message": "Shipment sync completed successfully",
            "data": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shipment sync failed: {str(e)}")

@router.post("/full")
async def full_sync_endpoint(
    shopify_limit: int = 250,
    shipment_limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Full sync: First sync Shopify orders, then sync shipment status
    """
    try:
        # Step 1: Sync Shopify orders
        shopify_result = await sync_shopify_dynamically(db, limit=shopify_limit)
        
        if shopify_result.get("status") == "FAILED":
            raise HTTPException(status_code=500, detail=f"Shopify sync failed: {shopify_result.get('error')}")
        
        # Step 2: Sync shipment status
        shipment_result = await sync_shipment_status_dynamically(db, limit=shipment_limit)
        
        return {
            "success": True,
            "message": "Full sync completed successfully",
            "data": {
                "shopify_sync": shopify_result,
                "shipment_sync": shipment_result
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Full sync failed: {str(e)}")

@router.get("/status")
async def get_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current sync status and statistics"""
    try:
        sync_service = DynamicShopifySync(db)
        
        # Get statistics
        from app.models import Shipment, Order
        
        total_orders = db.query(Order).count()
        total_shipments = db.query(Shipment).count()
        selloship_shipments = db.query(Shipment).filter(
            Shipment.courier_name.ilike('%selloship%')
        ).count()
        
        return {
            "success": True,
            "data": {
                "total_orders": total_orders,
                "total_shipments": total_shipments,
                "selloship_shipments": selloship_shipments,
                "shopify_configured": sync_service.get_shopify_account() is not None
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")
