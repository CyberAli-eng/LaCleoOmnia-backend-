"""
Logistics analytics endpoints - RTO dashboard and courier performance
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Order, OrderFinance, FulfilmentStatus, Shipment, ShipmentStatus, ChannelAccount

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_channel_account_ids(db: Session, user: User) -> list[str]:
    return [ca.id for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == user.id).all()]


@router.get("/rto")
async def get_logistics_rto(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get RTO analytics by courier for logistics dashboard.
    Returns courier-wise RTO percentage and loss amounts.
    """
    account_ids = _user_channel_account_ids(db, current_user)
    if not account_ids:
        return {"couriers": []}
    
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    try:
        # Base query for user's shipments
        base_query = (
            db.query(Shipment)
            .join(Order, Shipment.order_id == Order.id)
            .filter(Order.channel_account_id.in_(account_ids))
            .filter(Shipment.created_at >= start_date)
            .filter(Shipment.created_at <= end_date)
        )
        
        # Get total shipments by courier
        total_by_courier = (
            base_query.with_entities(
                Shipment.courier_name,
                func.count(Shipment.id).label('total_shipments')
            )
            .group_by(Shipment.courier_name)
            .all()
        )
        
        # Get RTO shipments by courier
        rto_by_courier = (
            base_query.filter(Shipment.status.in_([ShipmentStatus.RTO_INITIATED, ShipmentStatus.RTO_DONE]))
            .with_entities(
                Shipment.courier_name,
                func.count(Shipment.id).label('rto_shipments'),
                func.sum(Shipment.forward_cost + Shipment.reverse_cost).label('rto_loss')
            )
            .group_by(Shipment.courier_name)
            .all()
        )
        
        # Build courier stats
        total_map = {courier: total for courier, total in total_by_courier}
        rto_map = {}
        for courier, rto_count, loss in rto_by_courier:
            rto_map[courier] = {
                'rto_count': rto_count,
                'rto_loss': float(loss or 0)
            }
        
        couriers = []
        for courier in total_map.keys():
            total = total_map[courier]
            rto_data = rto_map.get(courier, {'rto_count': 0, 'rto_loss': 0})
            rto_count = rto_data['rto_count']
            rto_loss = rto_data['rto_loss']
            
            rto_percentage = (rto_count / total * 100) if total > 0 else 0
            
            couriers.append({
                "courier": courier,
                "total_shipments": total,
                "rto_shipments": rto_count,
                "rto_percentage": round(rto_percentage, 1),
                "rto_loss": rto_loss,
                "rto_loss_formatted": f"₹{rto_loss:,.0f}" if rto_loss > 0 else "₹0"
            })
        
        # Sort by RTO percentage descending
        couriers.sort(key=lambda x: x['rto_percentage'], reverse=True)
        
        return {
            "period_days": days,
            "couriers": couriers,
            "summary": {
                "total_shipments": sum(total_map.values()),
                "total_rto": sum(rto_map.get(c, {'rto_count': 0})['rto_count'] for c in total_map.keys()),
                "total_loss": sum(rto_map.get(c, {'rto_loss': 0})['rto_loss'] for c in total_map.keys())
            }
        }
        
    except Exception as e:
        logger.exception("Logistics RTO analytics failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch RTO analytics")

