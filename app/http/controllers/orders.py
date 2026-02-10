"""
Order routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models import Order, OrderItem, OrderStatus, User, FulfillmentStatus, Warehouse, Inventory, InventoryMovement, InventoryMovementType, Channel, ChannelAccount, AuditLog, AuditLogAction, OrderProfit
from app.auth import get_current_user
from app.services.warehouse_helper import get_default_warehouse
from app.http.requests import OrderResponse, ShipOrderRequest
from decimal import Decimal

router = APIRouter()

@router.get("", response_model=dict)
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    channel: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List orders with filters"""
    # Get channel accounts for the current user
    channel_accounts = db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()
    
    channel_account_ids = [ca.id for ca in channel_accounts]
    
    # Start query with user's orders only
    if channel_account_ids:
        query = db.query(Order).filter(
            Order.channel_account_id.in_(channel_account_ids)
        )
    else:
        # No channel accounts, return empty result
        return {"orders": []}
    
    if status_filter and status_filter != "all":
        query = query.filter(Order.status == status_filter)
    
    if channel:
        query = query.join(Order.channel).filter(Channel.name == channel)
    
    if q:
        query = query.filter(
            or_(
                Order.channel_order_id.contains(q),
                Order.customer_name.contains(q),
                Order.customer_email.contains(q)
            )
        )
    
    orders = query.order_by(Order.created_at.desc()).limit(100).all()
    
    result = []
    for order in orders:
        items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        result.append({
            "id": order.id,
            "channelOrderId": order.channel_order_id,
            "customerName": order.customer_name,
            "customerEmail": order.customer_email,
            "shippingAddress": getattr(order, "shipping_address", None) or None,
            "billingAddress": getattr(order, "billing_address", None) or None,
            "paymentMode": order.payment_mode.value,
            "orderTotal": float(order.order_total),
            "status": order.status.value,
            "createdAt": order.created_at.isoformat(),
            "items": [
                {
                    "id": item.id,
                    "sku": item.sku,
                    "title": item.title,
                    "qty": item.qty,
                    "price": float(item.price),
                    "fulfillmentStatus": item.fulfillment_status.value
                }
                for item in items
            ]
        })
    
    return {"orders": result}

@router.get("/{order_id}")
async def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get order details"""
    # Get channel accounts for the current user
    channel_accounts = db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()
    
    channel_account_ids = [ca.id for ca in channel_accounts]
    
    # Check if order belongs to user
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Verify order belongs to current user
    if order.channel_account_id not in channel_account_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    
    # Get shipment if exists
    from app.models import Shipment
    shipment = db.query(Shipment).filter(Shipment.order_id == order.id).first()
    # Get profit if computed
    profit = db.query(OrderProfit).filter(OrderProfit.order_id == order.id).first()

    return {
        "order": {
            "id": order.id,
            "channelOrderId": order.channel_order_id,
            "customerName": order.customer_name,
            "customerEmail": order.customer_email,
            "shippingAddress": getattr(order, "shipping_address", None) or None,
            "billingAddress": getattr(order, "billing_address", None) or None,
            "paymentMode": order.payment_mode.value,
            "orderTotal": float(order.order_total),
            "status": order.status.value,
            "createdAt": order.created_at.isoformat(),
            "updatedAt": order.updated_at.isoformat() if order.updated_at else None,
            "items": [
                {
                    "id": item.id,
                    "sku": item.sku,
                    "title": item.title,
                    "qty": item.qty,
                    "price": float(item.price),
                    "fulfillmentStatus": item.fulfillment_status.value,
                    "variantId": item.variant_id
                }
                for item in items
            ],
            "shipment": {
                "courierName": shipment.courier_name,
                "awbNumber": shipment.awb_number,
                "trackingUrl": shipment.tracking_url,
                "labelUrl": shipment.label_url,
                "status": shipment.status.value,
                "forwardCost": float(getattr(shipment, "forward_cost", None) or 0),
                "reverseCost": float(getattr(shipment, "reverse_cost", None) or 0),
                "shippedAt": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
                "lastSyncedAt": (lambda x: x.isoformat() if x else None)(getattr(shipment, "last_synced_at", None)),
            } if shipment else None,
            "profit": {
                "revenue": float(profit.revenue),
                "productCost": float(profit.product_cost),
                "packagingCost": float(profit.packaging_cost),
                "shippingCost": float(profit.shipping_cost),
                "shippingForward": float(getattr(profit, "shipping_forward", 0) or 0),
                "shippingReverse": float(getattr(profit, "shipping_reverse", 0) or 0),
                "marketingCost": float(profit.marketing_cost),
                "paymentFee": float(profit.payment_fee),
                "netProfit": float(profit.net_profit),
                "rtoLoss": float(getattr(profit, "rto_loss", 0) or 0),
                "lostLoss": float(getattr(profit, "lost_loss", 0) or 0),
                "courierStatus": getattr(profit, "courier_status", None),
                "finalStatus": getattr(profit, "final_status", None),
                "status": profit.status,
            } if profit else None
        }
    }

@router.post("/{order_id}/confirm")
async def confirm_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Confirm order (only for orders belonging to the current user)."""
    account_ids = [ca.id for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == current_user.id).all()]
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.channel_account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    if order.status not in [OrderStatus.NEW, OrderStatus.HOLD]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm order in {order.status.value} status"
        )
    
    # Check all items are mapped
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    unmapped_items = [item for item in items if item.fulfillment_status == FulfillmentStatus.UNMAPPED_SKU]
    
    if unmapped_items:
        raise HTTPException(
            status_code=400,
            detail="Cannot confirm order with unmapped SKUs",
            extra={"unmappedSkus": [item.sku for item in unmapped_items]}
        )
    
    # Check stock availability
    warehouse = db.query(Warehouse).filter(Warehouse.name == "Main Warehouse").first()
    if not warehouse:
        raise HTTPException(status_code=500, detail="Default warehouse not found")
    
    for item in items:
        if not item.variant_id:
            continue
        
        inventory = db.query(Inventory).filter(
            Inventory.warehouse_id == warehouse.id,
            Inventory.variant_id == item.variant_id
        ).first()
        
        available_qty = (inventory.total_qty if inventory else 0) - (inventory.reserved_qty if inventory else 0)
        
        if available_qty < item.qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for SKU {item.sku}. Available: {available_qty}, Required: {item.qty}"
            )
    
    # Update order status
    order.status = OrderStatus.CONFIRMED
    db.commit()
    db.refresh(order)
    
    # Log audit event
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.ORDER_CONFIRMED,
        entity_type="Order",
        entity_id=order.id,
        details={"previous_status": "NEW", "new_status": "CONFIRMED"}
    )
    db.add(audit_log)
    db.commit()
    
    return {"order": order}

@router.post("/{order_id}/pack")
async def pack_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Pack order (only for orders belonging to the current user)."""
    account_ids = [ca.id for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == current_user.id).all()]
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.channel_account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    if order.status != OrderStatus.CONFIRMED:
        raise HTTPException(
            status_code=400,
            detail=f"Order must be CONFIRMED to pack. Current status: {order.status.value}"
        )
    
    order.status = OrderStatus.PACKED
    db.commit()
    db.refresh(order)
    
    # Log audit event
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.ORDER_PACKED,
        entity_type="Order",
        entity_id=order.id,
        details={"previous_status": "CONFIRMED", "new_status": "PACKED"}
    )
    db.add(audit_log)
    db.commit()
    
    return {"order": order}

@router.post("/{order_id}/ship")
async def ship_order(
    order_id: str,
    request: ShipOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Ship order"""
    from app.models import Shipment, ShipmentStatus
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.PACKED:
        raise HTTPException(
            status_code=400,
            detail=f"Order must be PACKED to ship. Current status: {order.status.value}"
        )

    warehouse = get_default_warehouse(db)
    if not warehouse:
        raise HTTPException(status_code=500, detail="No warehouse configured. Create a warehouse or set DEFAULT_WAREHOUSE_NAME / DEFAULT_WAREHOUSE_ID.")
    
    # Update order status
    order.status = OrderStatus.SHIPPED
    
    # Create shipment
    shipment = Shipment(
        order_id=order_id,
        courier_name=request.courier_name or "delhivery",
        awb_number=request.awb_number,
        tracking_url=request.tracking_url,
        label_url=request.label_url,
        forward_cost=Decimal(str(getattr(request, "forward_cost", 0) or 0)),
        reverse_cost=Decimal(str(getattr(request, "reverse_cost", 0) or 0)),
        status=ShipmentStatus.SHIPPED,
        shipped_at=datetime.utcnow()
    )
    db.add(shipment)
    
    # Decrement inventory
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    for item in items:
        if not item.variant_id:
            continue
        
        inventory = db.query(Inventory).filter(
            Inventory.warehouse_id == warehouse.id,
            Inventory.variant_id == item.variant_id
        ).first()
        
        if inventory:
            inventory.total_qty -= item.qty
            inventory.reserved_qty -= item.qty
        
        # Log movement
        movement = InventoryMovement(
            warehouse_id=warehouse.id,
            variant_id=item.variant_id,
            type=InventoryMovementType.OUT,
            qty=item.qty,
            reference=order_id
        )
        db.add(movement)
    
    db.commit()
    
    from app.services.profit_calculator import compute_profit_for_order
    compute_profit_for_order(db, order_id)
    
    # Log audit events
    audit_log_order = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.ORDER_SHIPPED,
        entity_type="Order",
        entity_id=order.id,
        details={"previous_status": "PACKED", "new_status": "SHIPPED", "courier": request.courier_name}
    )
    audit_log_shipment = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.SHIPMENT_CREATED,
        entity_type="Shipment",
        entity_id=shipment.id,
        details={"awb_number": request.awb_number, "courier": request.courier_name}
    )
    db.add(audit_log_order)
    db.add(audit_log_shipment)
    db.commit()
    
    return {"order": order, "shipment": shipment}

@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel order (only for orders belonging to the current user)."""
    account_ids = [ca.id for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == current_user.id).all()]
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.channel_account_id not in account_ids:
        raise HTTPException(status_code=403, detail="Access denied")
    if order.status in [OrderStatus.SHIPPED, OrderStatus.DELIVERED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order in {order.status.value} status"
        )

    warehouse = get_default_warehouse(db)
    if not warehouse:
        raise HTTPException(status_code=500, detail="No warehouse configured. Create a warehouse or set DEFAULT_WAREHOUSE_NAME / DEFAULT_WAREHOUSE_ID.")
    
    # Release reserved inventory
    items = db.query(OrderItem).filter(OrderItem.order_id == order_id).all()
    for item in items:
        if not item.variant_id:
            continue
        
        inventory = db.query(Inventory).filter(
            Inventory.warehouse_id == warehouse.id,
            Inventory.variant_id == item.variant_id
        ).first()
        
        if inventory:
            inventory.reserved_qty -= item.qty
        
        # Log movement
        movement = InventoryMovement(
            warehouse_id=warehouse.id,
            variant_id=item.variant_id,
            type=InventoryMovementType.RELEASE,
            qty=item.qty,
            reference=order_id
        )
        db.add(movement)
    
    # Get previous status for audit log
    previous_status = order.status.value
    
    # Update order status
    order.status = OrderStatus.CANCELLED
    db.commit()
    db.refresh(order)
    
    # Log audit event
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.ORDER_CANCELLED,
        entity_type="Order",
        entity_id=order.id,
        details={"previous_status": previous_status, "new_status": "CANCELLED"}
    )
    db.add(audit_log)
    db.commit()
    
    return {"order": order}
