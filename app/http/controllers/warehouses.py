"""
Warehouse routes
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Warehouse, User
from app.auth import get_current_user
from app.http.requests import WarehouseCreateRequest

router = APIRouter()

@router.get("")
async def list_warehouses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List warehouses"""
    warehouses = db.query(Warehouse).all()
    return {
        "warehouses": [
            {
                "id": w.id,
                "name": w.name,
                "city": w.city,
                "state": w.state,
                "createdAt": w.created_at.isoformat() if w.created_at else None
            }
            for w in warehouses
        ]
    }

@router.post("")
async def create_warehouse(
    request: WarehouseCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create warehouse"""
    warehouse = Warehouse(
        name=request.name,
        city=request.city,
        state=request.state
    )
    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)
    return {"warehouse": warehouse}

@router.patch("/{warehouse_id}")
async def update_warehouse(
    warehouse_id: str,
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update warehouse"""
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=404, detail="Warehouse not found")
    
    if "name" in request:
        warehouse.name = request["name"]
    if "city" in request:
        warehouse.city = request["city"]
    if "state" in request:
        warehouse.state = request["state"]
    
    db.commit()
    db.refresh(warehouse)
    return {"warehouse": warehouse}
