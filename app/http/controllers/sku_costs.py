"""
SKU cost engine: CRUD for product_cost, packaging, box, inbound. Required for profit calculation.
"""
import csv
import io
import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, File, HTTPException, status, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SkuCost, User
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class SkuCostCreate(BaseModel):
    sku: str
    product_cost: float = 0.0
    packaging_cost: float = 0.0
    box_cost: float = 0.0
    inbound_cost: float = 0.0


class SkuCostUpdate(BaseModel):
    product_cost: float | None = None
    packaging_cost: float | None = None
    box_cost: float | None = None
    inbound_cost: float | None = None


class SkuCostResponse(BaseModel):
    id: str
    sku: str
    product_cost: float
    packaging_cost: float
    box_cost: float
    inbound_cost: float
    created_at: str | None
    updated_at: str | None

    class Config:
        from_attributes = True


def _to_response(row: SkuCost) -> dict:
    return {
        "id": row.id,
        "sku": row.sku,
        "product_cost": float(row.product_cost or 0),
        "packaging_cost": float(row.packaging_cost or 0),
        "box_cost": float(row.box_cost or 0),
        "inbound_cost": float(row.inbound_cost or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("", response_model=list)
async def list_sku_costs(
    q: str | None = Query(None, description="Filter by SKU (substring)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all SKU costs. Optional ?q= to filter by SKU substring."""
    query = db.query(SkuCost)
    if q and q.strip():
        query = query.filter(SkuCost.sku.ilike(f"%{q.strip()}%"))
    rows = query.order_by(SkuCost.sku).all()
    return [_to_response(r) for r in rows]


@router.post("/bulk", response_model=dict)
async def bulk_upload_sku_costs(
    file: UploadFile = File(..., description="CSV with columns: sku, product_cost, packaging_cost, box_cost, inbound_cost"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk upsert SKU costs from CSV. Header: sku, product_cost, packaging_cost, box_cost, inbound_cost."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    try:
        body = await file.read()
    except Exception as e:
        logger.warning("Bulk upload read error: %s", e)
        raise HTTPException(status_code=400, detail="Failed to read file")
    try:
        text = body.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV has no header row")
        def norm(k: str) -> str:
            return (k or "").strip().lower().replace(" ", "_")
        field_map = {norm(f): f for f in reader.fieldnames}
        if "sku" not in field_map:
            raise HTTPException(status_code=400, detail="CSV must have a 'sku' column")
        created = 0
        updated = 0
        errors: list[str] = []
        for i, row in enumerate(reader):
            try:
                sku_key = field_map.get("sku", "sku")
                sku = (row.get(sku_key) or "").strip()
                if not sku:
                    continue
                product_cost = float(row.get(field_map.get("product_cost", "product_cost")) or 0)
                packaging_cost = float(row.get(field_map.get("packaging_cost", "packaging_cost")) or 0)
                box_cost = float(row.get(field_map.get("box_cost", "box_cost")) or 0)
                inbound_cost = float(row.get(field_map.get("inbound_cost", "inbound_cost")) or 0)
            except (ValueError, TypeError) as e:
                errors.append(f"Row {i + 2}: invalid number - {e}")
                continue
            existing = db.query(SkuCost).filter(SkuCost.sku == sku).first()
            if existing:
                existing.product_cost = Decimal(str(product_cost))
                existing.packaging_cost = Decimal(str(packaging_cost))
                existing.box_cost = Decimal(str(box_cost))
                existing.inbound_cost = Decimal(str(inbound_cost))
                updated += 1
            else:
                db.add(SkuCost(
                    sku=sku,
                    product_cost=Decimal(str(product_cost)),
                    packaging_cost=Decimal(str(packaging_cost)),
                    box_cost=Decimal(str(box_cost)),
                    inbound_cost=Decimal(str(inbound_cost)),
                ))
                created += 1
        db.commit()
        return {"created": created, "updated": updated, "errors": errors[:50]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Bulk upload failed: %s", e)
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")


@router.get("/{sku}", response_model=dict)
async def get_sku_cost(
    sku: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get cost for one SKU."""
    row = db.query(SkuCost).filter(SkuCost.sku == sku).first()
    if not row:
        raise HTTPException(status_code=404, detail="SKU cost not found")
    return _to_response(row)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=dict)
async def create_sku_cost(
    body: SkuCostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or replace SKU cost (upsert by SKU)."""
    sku = (body.sku or "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="sku is required")
    existing = db.query(SkuCost).filter(SkuCost.sku == sku).first()
    if existing:
        existing.product_cost = Decimal(str(body.product_cost))
        existing.packaging_cost = Decimal(str(body.packaging_cost))
        existing.box_cost = Decimal(str(body.box_cost))
        existing.inbound_cost = Decimal(str(body.inbound_cost))
        db.commit()
        db.refresh(existing)
        return _to_response(existing)
    row = SkuCost(
        sku=sku,
        product_cost=Decimal(str(body.product_cost)),
        packaging_cost=Decimal(str(body.packaging_cost)),
        box_cost=Decimal(str(body.box_cost)),
        inbound_cost=Decimal(str(body.inbound_cost)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.patch("/{sku}", response_model=dict)
async def update_sku_cost(
    sku: str,
    body: SkuCostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update SKU cost (partial)."""
    row = db.query(SkuCost).filter(SkuCost.sku == sku).first()
    if not row:
        raise HTTPException(status_code=404, detail="SKU cost not found")
    if body.product_cost is not None:
        row.product_cost = Decimal(str(body.product_cost))
    if body.packaging_cost is not None:
        row.packaging_cost = Decimal(str(body.packaging_cost))
    if body.box_cost is not None:
        row.box_cost = Decimal(str(body.box_cost))
    if body.inbound_cost is not None:
        row.inbound_cost = Decimal(str(body.inbound_cost))
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.delete("/{sku}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sku_cost(
    sku: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete SKU cost."""
    row = db.query(SkuCost).filter(SkuCost.sku == sku).first()
    if not row:
        raise HTTPException(status_code=404, detail="SKU cost not found")
    db.delete(row)
    db.commit()
