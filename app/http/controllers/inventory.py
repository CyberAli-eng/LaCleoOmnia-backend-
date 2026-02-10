"""
Inventory routes. List inventory is scoped to the current user's channels:
only variants that appear in orders from the user's connected channel accounts are shown.
If no marketplace is connected, inventory list is empty.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models import (
    Inventory,
    Warehouse,
    ProductVariant,
    InventoryMovement,
    InventoryMovementType,
    User,
    AuditLog,
    AuditLogAction,
    ChannelAccount,
    Order,
    OrderItem,
)
from app.auth import get_current_user
from app.http.requests import InventoryAdjustRequest, InventoryResponse

router = APIRouter()


@router.get("", response_model=dict)
async def list_inventory(
    warehouse_id: Optional[str] = Query(None),
    sku: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List inventory scoped to current user: only variants from their channel orders. No channels => empty."""
    user_account_ids = [
        acc.id for acc in db.query(ChannelAccount).filter(
            ChannelAccount.user_id == current_user.id
        ).all()
    ]
    if not user_account_ids:
        return {"inventory": []}

    # Variant IDs that appear in this user's orders (scope inventory to user's channels)
    variant_ids = [
        r[0]
        for r in db.query(OrderItem.variant_id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.channel_account_id.in_(user_account_ids),
            OrderItem.variant_id.isnot(None),
        )
        .distinct()
        .all()
    ]
    if not variant_ids:
        return {"inventory": []}

    query = db.query(Inventory).filter(Inventory.variant_id.in_(variant_ids))

    if warehouse_id:
        query = query.filter(Inventory.warehouse_id == warehouse_id)

    if sku:
        query = query.join(ProductVariant).filter(ProductVariant.sku.contains(sku))

    inventory_list = query.all()
    
    result = []
    for inv in inventory_list:
        result.append({
            "id": inv.id,
            "warehouseId": inv.warehouse_id,
            "warehouse": {
                "id": inv.warehouse.id,
                "name": inv.warehouse.name,
                "city": inv.warehouse.city,
                "state": inv.warehouse.state
            },
            "variantId": inv.variant_id,
            "variant": {
                "id": inv.variant.id,
                "sku": inv.variant.sku,
                "product": {
                    "id": inv.variant.product.id,
                    "title": inv.variant.product.title,
                    "brand": inv.variant.product.brand
                }
            },
            "totalQty": inv.total_qty,
            "reservedQty": inv.reserved_qty,
            "availableQty": inv.total_qty - inv.reserved_qty
        })
    
    return {"inventory": result}

@router.post("/adjust")
async def adjust_inventory(
    request: InventoryAdjustRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Adjust inventory"""
    # Find variant by SKU
    variant = db.query(ProductVariant).filter(ProductVariant.sku == request.sku).first()
    if not variant:
        raise HTTPException(status_code=404, detail=f"Variant with SKU {request.sku} not found")
    
    # Get or create inventory record
    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == request.warehouse_id,
        Inventory.variant_id == variant.id
    ).first()
    
    if inventory:
        inventory.total_qty += request.qty_delta
    else:
        inventory = Inventory(
            warehouse_id=request.warehouse_id,
            variant_id=variant.id,
            total_qty=request.qty_delta if request.qty_delta > 0 else 0,
            reserved_qty=0
        )
        db.add(inventory)
    
    # Prevent negative inventory
    if inventory.total_qty < 0:
        raise HTTPException(status_code=400, detail="Cannot adjust inventory below zero")
    
    # Log movement
    movement = InventoryMovement(
        warehouse_id=request.warehouse_id,
        variant_id=variant.id,
        type=InventoryMovementType.IN if request.qty_delta > 0 else InventoryMovementType.OUT,
        qty=abs(request.qty_delta),
        reference=request.reason
    )
    db.add(movement)
    db.commit()
    db.refresh(inventory)
    
    # Log audit event
    audit_log = AuditLog(
        user_id=current_user.id,
        action=AuditLogAction.INVENTORY_ADJUSTED,
        entity_type="Inventory",
        entity_id=inventory.id,
        details={
            "sku": request.sku,
            "warehouse_id": request.warehouse_id,
            "qty_delta": request.qty_delta,
            "reason": request.reason,
            "new_total_qty": inventory.total_qty
        }
    )
    db.add(audit_log)
    db.commit()
    
    return {
        "inventory": {
            "id": inventory.id,
            "warehouseId": inventory.warehouse_id,
            "variantId": inventory.variant_id,
            "totalQty": inventory.total_qty,
            "reservedQty": inventory.reserved_qty,
            "availableQty": inventory.total_qty - inventory.reserved_qty
        }
    }
