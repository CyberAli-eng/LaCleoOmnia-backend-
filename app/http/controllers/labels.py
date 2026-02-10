"""
Label generation routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Order, User, Label, ChannelAccount
from app.auth import get_current_user
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class GenerateLabelRequest(BaseModel):
    orderId: Optional[int] = None
    orderIds: Optional[List[int]] = None

@router.get("")
async def list_labels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all labels for the current user"""
    labels = db.query(Label).filter(Label.user_id == current_user.id).all()
    
    return [
        {
            "id": label.id,
            "orderId": label.order_id,
            "trackingNumber": label.tracking_number,
            "carrier": label.carrier,
            "status": label.status.value if label.status else None,
            "createdAt": label.created_at.isoformat() if label.created_at else None,
        }
        for label in labels
    ]

@router.post("/generate")
async def generate_labels(
    request: GenerateLabelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate shipping labels for orders"""
    # Handle both single orderId and orderIds array
    order_ids = []
    if request.orderId:
        order_ids = [request.orderId]
    elif request.orderIds:
        order_ids = request.orderIds
    else:
        raise HTTPException(
            status_code=400,
            detail="orderId or orderIds is required"
        )
    
    # Get channel accounts for the current user
    channel_accounts = db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()
    
    channel_account_ids = [ca.id for ca in channel_accounts]
    
    # Get orders that belong to user's channel accounts
    if channel_account_ids:
        orders = db.query(Order).filter(
            Order.id.in_([str(oid) for oid in order_ids]),
            Order.channel_account_id.in_(channel_account_ids)
        ).all()
    else:
        orders = []
    
    if len(orders) != len(order_ids):
        raise HTTPException(
            status_code=404,
            detail="Some orders not found"
        )
    
    generated_labels = []
    for order in orders:
        # Check if label already exists
        existing = db.query(Label).filter(Label.order_id == order.id).first()
        if existing:
            generated_labels.append({
                "id": existing.id,
                "orderId": existing.order_id,
                "trackingNumber": existing.tracking_number,
                "carrier": existing.carrier,
            })
            continue
        
        # Generate a placeholder label (in production, integrate with shipping API)
        # Use order.id as string if it's already a string, otherwise convert
        order_id_str = str(order.id) if isinstance(order.id, str) else order.id
        label = Label(
            order_id=order_id_str,
            user_id=str(current_user.id),
            tracking_number=f"TRACK{order.id:08d}",
            carrier="Standard",
            status="PENDING"
        )
        db.add(label)
        generated_labels.append({
            "id": label.id,
            "orderId": label.order_id,
            "trackingNumber": label.tracking_number,
            "carrier": label.carrier,
        })
    
    db.commit()
    
    return {
        "labels": generated_labels,
        "message": f"Generated {len(generated_labels)} labels"
    }
