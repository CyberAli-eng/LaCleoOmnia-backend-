"""
Persist Shopify inventory to DB: ShopifyInventory cache + Inventory (Warehouse/ProductVariant).
Used by POST /shopify/sync and by SyncEngine.sync_inventory so one code path.
"""
import logging
from sqlalchemy.orm import Session
from decimal import Decimal

from app.models import (
    ShopifyInventory,
    Warehouse,
    Product,
    ProductVariant,
    Inventory,
)

logger = logging.getLogger(__name__)


def persist_shopify_inventory(db: Session, shop_domain: str, inv_list: list) -> int:
    """
    Upsert inventory into shopify_inventory cache and into Inventory (Shopify warehouse).
    inv_list: list of dicts with sku, product_name, variant_id, inventory_item_id, location_id, available.
    Returns number of inventory records updated/inserted (for Inventory table; cache is full replace).
    """
    if not inv_list:
        return 0

    # 1) Replace shopify_inventory cache for this shop (do not rollback; caller may have other changes)
    try:
        db.query(ShopifyInventory).filter(ShopifyInventory.shop_domain == shop_domain).delete()
        for row in inv_list:
            if not isinstance(row, dict):
                continue
            sku = (row.get("sku") or "—").strip()
            if sku == "—":
                continue
            r = ShopifyInventory(
                shop_domain=shop_domain,
                sku=sku[:255],
                product_name=((row.get("product_name") or sku) or "")[:255],
                variant_id=str(row.get("variant_id") or "")[:64] if row.get("variant_id") else None,
                inventory_item_id=str(row.get("inventory_item_id") or "")[:64] if row.get("inventory_item_id") else None,
                location_id=str(row.get("location_id") or "")[:64] if row.get("location_id") else None,
                available=int(row.get("available", 0) or 0),
            )
            db.add(r)
    except Exception as e:
        logger.warning("Failed to update ShopifyInventory cache: %s", e)

    # 2) Upsert into Inventory (Warehouse "Shopify", Product "Shopify Products")
    inventory_synced = 0
    try:
        warehouse = db.query(Warehouse).filter(Warehouse.name == "Shopify").first()
        if not warehouse:
            warehouse = Warehouse(name="Shopify", city=None, state=None)
            db.add(warehouse)
            db.flush()
        product = db.query(Product).filter(Product.title == "Shopify Products").first()
        if not product:
            product = Product(title="Shopify Products", brand=None, category=None)
            db.add(product)
            db.flush()
        for row in inv_list:
            if not isinstance(row, dict):
                continue
            sku = (row.get("sku") or "").strip() or "—"
            if sku == "—":
                continue
            product_name = ((row.get("product_name") or sku) or "—")[:255]
            available = int(row.get("available", 0) or 0)
            variant = db.query(ProductVariant).filter(ProductVariant.sku == sku).first()
            if not variant:
                variant = ProductVariant(
                    product_id=product.id,
                    sku=sku,
                    mrp=Decimal("0"),
                    selling_price=Decimal("0"),
                )
                db.add(variant)
                db.flush()
            inv = db.query(Inventory).filter(
                Inventory.warehouse_id == warehouse.id,
                Inventory.variant_id == variant.id,
            ).first()
            if not inv:
                inv = Inventory(
                    warehouse_id=warehouse.id,
                    variant_id=variant.id,
                    total_qty=available,
                    reserved_qty=0,
                )
                db.add(inv)
                inventory_synced += 1
            else:
                if inv.total_qty != available:
                    inv.total_qty = available
                    inventory_synced += 1
    except Exception as e:
        logger.exception("Inventory DB sync failed: %s", e)
        return 0

    return inventory_synced
