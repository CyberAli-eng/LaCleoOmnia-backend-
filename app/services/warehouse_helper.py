"""Default warehouse resolution for order operations (confirm, pack, ship, cancel)."""
from sqlalchemy.orm import Session

from app.models import Warehouse
from app.config import settings


def get_default_warehouse(db: Session):
    """
    Return the default warehouse for inventory operations.
    Uses DEFAULT_WAREHOUSE_ID if set, else DEFAULT_WAREHOUSE_NAME, else first warehouse.
    """
    if getattr(settings, "DEFAULT_WAREHOUSE_ID", ""):
        wh = db.query(Warehouse).filter(Warehouse.id == settings.DEFAULT_WAREHOUSE_ID).first()
        if wh:
            return wh
    name = getattr(settings, "DEFAULT_WAREHOUSE_NAME", "Main Warehouse") or "Main Warehouse"
    wh = db.query(Warehouse).filter(Warehouse.name == name).first()
    if wh:
        return wh
    return db.query(Warehouse).order_by(Warehouse.created_at).first()
