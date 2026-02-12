"""
Fulfilled Orders Sync - Specifically fetch Shopify fulfilled orders with tracking
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Order, Channel, ChannelType
from app.auth import get_current_user
from app.services.shopify import ShopifyService
from app.http.controllers.integrations import _get_shopify_integration

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/sync-fulfilled")
async def sync_fulfilled_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sync specifically fulfilled orders from Shopify with tracking data
    """
    try:
        # Get Shopify integration
        shopify_integration = _get_shopify_integration(db, current_user)
        if not shopify_integration:
            raise HTTPException(status_code=404, detail="Shopify not connected")
        
        # Initialize Shopify service
        shopify_service = ShopifyService(shopify_integration)
        
        # Get ONLY fulfilled orders from Shopify
        logger.info("Fetching fulfilled orders from Shopify...")
        fulfilled_orders = await shopify_service.get_fulfilled_orders(limit=250)
        logger.info(f"Found {len(fulfilled_orders)} fulfilled orders from Shopify")
        
        synced_count = 0
        updated_count = 0
        
        for shopify_order in fulfilled_orders:
            try:
                # Check if order already exists
                existing_order = db.query(Order).filter(
                    Order.channel_order_id == str(shopify_order.get('id')),
                    Order.user_id == current_user.id
                ).first()
                
                if existing_order:
                    # Update existing order status and add tracking info
                    if existing_order.status != 'FULFILLED':
                        existing_order.status = 'FULFILLED'
                        updated_count += 1
                        logger.info(f"Updated order {shopify_order.get('id')} to FULFILLED")
                else:
                    # Create new order (shouldn't happen for fulfilled orders, but just in case)
                    logger.warning(f"Fulfilled order {shopify_order.get('id')} not found in database")
                
                # Process fulfillments for tracking
                fulfillments = shopify_order.get('fulfillments', [])
                for fulfillment in fulfillments:
                    tracking_number = fulfillment.get('tracking_number')
                    if tracking_number:
                        logger.info(f"Order {shopify_order.get('id')} has tracking {tracking_number}")
                
                synced_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process fulfilled order {shopify_order.get('id')}: {e}")
                continue
        
        db.commit()
        
        return {
            "message": f"Synced {synced_count} fulfilled orders",
            "synced_count": synced_count,
            "updated_count": updated_count,
            "fulfilled_orders_from_shopify": len(fulfilled_orders)
        }
        
    except Exception as e:
        logger.exception("Failed to sync fulfilled orders")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/shopify-fulfilled")
async def get_shopify_fulfilled_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get fulfilled orders directly from Shopify (without storing)
    """
    try:
        # Get Shopify integration
        shopify_integration = _get_shopify_integration(db, current_user)
        if not shopify_integration:
            raise HTTPException(status_code=404, detail="Shopify not connected")
        
        # Initialize Shopify service
        shopify_service = ShopifyService(shopify_integration)
        
        # Get fulfilled orders from Shopify
        fulfilled_orders = await shopify_service.get_fulfilled_orders(limit=50)
        
        # Extract tracking info
        tracking_info = []
        for order in fulfilled_orders:
            fulfillments = order.get('fulfillments', [])
            for fulfillment in fulfillments:
                tracking_info.append({
                    "order_id": order.get('id'),
                    "channel_order_id": order.get('name'),
                    "customer": order.get('customer', {}).get('first_name', '') + ' ' + order.get('customer', {}).get('last_name', ''),
                    "tracking_number": fulfillment.get('tracking_number'),
                    "tracking_company": fulfillment.get('tracking_company'),
                    "fulfillment_status": fulfillment.get('status'),
                    "created_at": order.get('created_at'),
                    "financial_status": order.get('financial_status'),
                    "fulfillment_status": order.get('fulfillment_status')
                })
        
        return {
            "fulfilled_orders_count": len(fulfilled_orders),
            "tracking_info": tracking_info
        }
        
    except Exception as e:
        logger.exception("Failed to get Shopify fulfilled orders")
        raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")
