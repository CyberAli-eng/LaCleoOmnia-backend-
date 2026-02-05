"""
Order import service for Shopify, Amazon, Flipkart, Myntra.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    ChannelAccount,
    Order,
    OrderItem,
    OrderStatus,
    PaymentMode,
    FulfillmentStatus,
    ProductVariant,
    Inventory,
    InventoryMovement,
    InventoryMovementType,
    Warehouse,
    SyncJob,
    SyncJobType,
    SyncJobStatus,
    SyncLog,
    LogLevel,
)
from app.services.shopify import ShopifyService
from app.services.warehouse_helper import get_default_warehouse
from app.services.credentials import get_provider_credentials
from app.services.amazon_service import (
    get_lwa_access_token,
    get_orders as amazon_get_orders,
    normalize_amazon_order_to_common,
    DEFAULT_MARKETPLACE_ID,
)
from app.services.flipkart_service import (
    get_access_token as flipkart_get_token,
    get_orders as flipkart_get_orders,
    normalize_flipkart_order_item_to_common,
)
from app.services.myntra_service import get_orders as myntra_get_orders, normalize_myntra_order_to_common

async def import_shopify_orders(db: Session, account: ChannelAccount) -> dict:
    """Import orders from Shopify"""
    service = ShopifyService(account)
    
    # Create sync job
    sync_job = SyncJob(
        channel_account_id=account.id,
        job_type=SyncJobType.PULL_ORDERS,
        status=SyncJobStatus.RUNNING,
        started_at=datetime.utcnow()
    )
    db.add(sync_job)
    db.commit()
    db.refresh(sync_job)
    
    try:
        # Get default warehouse
        warehouse = get_default_warehouse(db)
        if not warehouse:
            raise Exception("No warehouse configured. Create a warehouse or set DEFAULT_WAREHOUSE_NAME / DEFAULT_WAREHOUSE_ID.")
        
        # Fetch orders from Shopify
        shopify_orders = await service.get_orders()
        
        imported = 0
        skipped = 0
        errors = 0
        
        for shopify_order in shopify_orders:
            try:
                # Check if order already exists (idempotent)
                existing = db.query(Order).filter(
                    Order.channel_id == account.channel_id,
                    Order.channel_order_id == str(shopify_order["id"])
                ).first()
                
                if existing:
                    skipped += 1
                    continue
                
                # Determine payment mode
                payment_mode = PaymentMode.PREPAID if shopify_order.get("financial_status") == "paid" else PaymentMode.COD
                
                # Extract customer info
                shipping_address = shopify_order.get("shipping_address", {})
                customer = shopify_order.get("customer", {})
                customer_name = (
                    shipping_address.get("name") or
                    f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or
                    "Unknown"
                )
                customer_email = shopify_order.get("email")
                
                # Process order items
                order_items_data = []
                all_mapped = True
                all_stock_available = True
                
                for line_item in shopify_order.get("line_items", []):
                    sku = line_item.get("sku", "")
                    variant = db.query(ProductVariant).filter(ProductVariant.sku == sku).first()
                    
                    fulfillment_status = FulfillmentStatus.PENDING
                    variant_id = None
                    
                    if variant:
                        fulfillment_status = FulfillmentStatus.MAPPED
                        variant_id = variant.id
                        
                        # Check inventory availability
                        inventory = db.query(Inventory).filter(
                            Inventory.warehouse_id == warehouse.id,
                            Inventory.variant_id == variant.id
                        ).first()
                        
                        available_qty = (inventory.total_qty if inventory else 0) - (inventory.reserved_qty if inventory else 0)
                        
                        if available_qty < line_item.get("quantity", 0):
                            all_stock_available = False
                    else:
                        fulfillment_status = FulfillmentStatus.UNMAPPED_SKU
                        all_mapped = False
                    
                    order_items_data.append({
                        "variant_id": variant_id,
                        "sku": sku,
                        "title": line_item.get("title", ""),
                        "qty": line_item.get("quantity", 0),
                        "price": Decimal(str(line_item.get("price", 0))),
                        "fulfillment_status": fulfillment_status
                    })
                
                # Determine order status
                order_status = OrderStatus.NEW
                if not all_mapped or not all_stock_available:
                    order_status = OrderStatus.HOLD
                
                # Create order
                order = Order(
                    channel_id=account.channel_id,
                    channel_account_id=account.id,
                    channel_order_id=str(shopify_order["id"]),
                    customer_name=customer_name,
                    customer_email=customer_email,
                    payment_mode=payment_mode,
                    order_total=Decimal(str(shopify_order.get("total_price", 0))),
                    status=order_status
                )
                db.add(order)
                db.flush()
                
                # Create order items
                for item_data in order_items_data:
                    order_item = OrderItem(
                        order_id=order.id,
                        variant_id=item_data["variant_id"],
                        sku=item_data["sku"],
                        title=item_data["title"],
                        qty=item_data["qty"],
                        price=item_data["price"],
                        fulfillment_status=item_data["fulfillment_status"]
                    )
                    db.add(order_item)
                    
                    # Reserve inventory for mapped items
                    if item_data["variant_id"] and item_data["fulfillment_status"] == FulfillmentStatus.MAPPED:
                        inventory = db.query(Inventory).filter(
                            Inventory.warehouse_id == warehouse.id,
                            Inventory.variant_id == item_data["variant_id"]
                        ).first()
                        
                        if inventory:
                            inventory.reserved_qty += item_data["qty"]
                        else:
                            inventory = Inventory(
                                warehouse_id=warehouse.id,
                                variant_id=item_data["variant_id"],
                                total_qty=0,
                                reserved_qty=item_data["qty"]
                            )
                            db.add(inventory)
                        
                        # Log inventory movement
                        movement = InventoryMovement(
                            warehouse_id=warehouse.id,
                            variant_id=item_data["variant_id"],
                            type=InventoryMovementType.RESERVE,
                            qty=item_data["qty"],
                            reference=order.id
                        )
                        db.add(movement)
                
                db.commit()
                imported += 1
                
                # Log success
                log = SyncLog(
                    sync_job_id=sync_job.id,
                    level=LogLevel.INFO,
                    message=f"Imported order {order.id} from Shopify order {shopify_order['id']}",
                    raw_payload=shopify_order
                )
                db.add(log)
                db.commit()
                
            except Exception as e:
                errors += 1
                log = SyncLog(
                    sync_job_id=sync_job.id,
                    level=LogLevel.ERROR,
                    message=f"Failed to import Shopify order {shopify_order.get('id', 'unknown')}: {str(e)}",
                    raw_payload=shopify_order
                )
                db.add(log)
                db.commit()
        
        # Update sync job
        sync_job.status = SyncJobStatus.SUCCESS
        sync_job.finished_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "jobId": sync_job.id
        }
        
    except Exception as e:
        sync_job.status = SyncJobStatus.FAILED
        sync_job.finished_at = datetime.utcnow()
        log = SyncLog(
            sync_job_id=sync_job.id,
            level=LogLevel.ERROR,
            message=f"Import failed: {str(e)}"
        )
        db.add(log)
        db.commit()
        raise


def _persist_one_common_order(
    db: Session,
    account: ChannelAccount,
    warehouse: Warehouse,
    common: dict,
    sync_job: SyncJob,
) -> tuple[bool, str | None]:
    """Create Order + OrderItems from a common-order dict. Returns (imported, None) or (False, 'skipped'/'error')."""
    channel_order_id = str(common.get("channel_order_id") or common.get("id") or "")
    if not channel_order_id:
        return False, "missing channel_order_id"
    existing = db.query(Order).filter(
        Order.channel_account_id == account.id,
        Order.channel_order_id == channel_order_id,
    ).first()
    if existing:
        return False, "skipped"

    payment_mode = PaymentMode.PREPAID if (common.get("payment_mode") or common.get("financial_status")) in ("PREPAID", "paid") else PaymentMode.COD
    order_total = Decimal(str(common.get("order_total", 0)))
    customer_name = (common.get("customer_name") or "Customer").strip() or "Customer"
    customer_email = (common.get("customer_email") or "").strip() or None
    items = common.get("items") or []

    order_items_data = []
    all_mapped = True
    all_stock_available = True
    for it in items:
        sku = str(it.get("sku") or "").strip() or f"LINE-{len(order_items_data)}"
        variant = db.query(ProductVariant).filter(ProductVariant.sku == sku).first()
        fulfillment_status = FulfillmentStatus.MAPPED if variant else FulfillmentStatus.UNMAPPED_SKU
        variant_id = variant.id if variant else None
        if not variant:
            all_mapped = False
        elif warehouse:
            inv = db.query(Inventory).filter(
                Inventory.warehouse_id == warehouse.id,
                Inventory.variant_id == variant.id,
            ).first()
            available = (inv.total_qty if inv else 0) - (inv.reserved_qty if inv else 0)
            if available < int(it.get("quantity") or 1):
                all_stock_available = False
        order_items_data.append({
            "variant_id": variant_id,
            "sku": sku,
            "title": str(it.get("title") or "Item").strip() or "Item",
            "qty": int(it.get("quantity") or 1),
            "price": Decimal(str(it.get("price") or 0)),
            "fulfillment_status": fulfillment_status,
        })

    order_status = OrderStatus.NEW if (all_mapped and all_stock_available) else OrderStatus.HOLD
    order = Order(
        channel_id=account.channel_id,
        channel_account_id=account.id,
        channel_order_id=channel_order_id,
        customer_name=customer_name,
        customer_email=customer_email,
        payment_mode=payment_mode,
        order_total=order_total,
        status=order_status,
    )
    db.add(order)
    db.flush()
    for item_data in order_items_data:
        oi = OrderItem(
            order_id=order.id,
            variant_id=item_data["variant_id"],
            sku=item_data["sku"],
            title=item_data["title"],
            qty=item_data["qty"],
            price=item_data["price"],
            fulfillment_status=item_data["fulfillment_status"],
        )
        db.add(oi)
        if item_data["variant_id"] and item_data["fulfillment_status"] == FulfillmentStatus.MAPPED and warehouse:
            inv = db.query(Inventory).filter(
                Inventory.warehouse_id == warehouse.id,
                Inventory.variant_id == item_data["variant_id"],
            ).first()
            if inv:
                inv.reserved_qty += item_data["qty"]
            else:
                inv = Inventory(
                    warehouse_id=warehouse.id,
                    variant_id=item_data["variant_id"],
                    total_qty=0,
                    reserved_qty=item_data["qty"],
                )
                db.add(inv)
            db.add(InventoryMovement(
                warehouse_id=warehouse.id,
                variant_id=item_data["variant_id"],
                type=InventoryMovementType.RESERVE,
                qty=item_data["qty"],
                reference=order.id,
            ))
    db.commit()
    db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.INFO, message=f"Imported order {order.id} ({channel_order_id})", raw_payload=common))
    db.commit()
    return True, None


async def import_amazon_orders(db: Session, account: ChannelAccount) -> dict:
    """Import orders from Amazon SP-API for the given channel account."""
    creds = get_provider_credentials(db, str(account.user_id), "amazon")
    if not creds or not creds.get("refresh_token") or not creds.get("client_id") or not creds.get("client_secret"):
        raise ValueError("Amazon credentials missing. Add Seller ID, Refresh Token, Client ID, and Client Secret in Integrations.")
    seller_id = (creds.get("seller_id") or "").strip() or account.seller_name
    marketplace_id = (creds.get("marketplace_id") or "").strip() or DEFAULT_MARKETPLACE_ID

    access_token = await get_lwa_access_token(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
        refresh_token=creds["refresh_token"],
    )
    created_after = datetime.now(timezone.utc) - timedelta(days=90)
    raw_orders = await amazon_get_orders(
        access_token=access_token,
        seller_id=seller_id,
        marketplace_id=marketplace_id,
        created_after=created_after,
    )

    warehouse = get_default_warehouse(db)
    if not warehouse:
        raise Exception("No warehouse configured. Create a warehouse or set DEFAULT_WAREHOUSE_NAME.")
    sync_job = SyncJob(
        channel_account_id=account.id,
        job_type=SyncJobType.PULL_ORDERS,
        status=SyncJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(sync_job)
    db.commit()
    db.refresh(sync_job)
    imported = 0
    skipped = 0
    errors = 0
    try:
        for raw in raw_orders:
            try:
                common = normalize_amazon_order_to_common(raw)
                ok, msg = _persist_one_common_order(db, account, warehouse, common, sync_job)
                if ok:
                    imported += 1
                elif msg == "skipped":
                    skipped += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.ERROR, message=str(e), raw_payload=raw))
                db.commit()
        sync_job.status = SyncJobStatus.SUCCESS
        sync_job.finished_at = datetime.now(timezone.utc)
        sync_job.records_processed = imported
        sync_job.records_failed = errors
        db.commit()
        return {"success": True, "imported": imported, "skipped": skipped, "errors": errors, "jobId": sync_job.id}
    except Exception as e:
        sync_job.status = SyncJobStatus.FAILED
        sync_job.finished_at = datetime.now(timezone.utc)
        sync_job.error_message = str(e)
        db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.ERROR, message=str(e)))
        db.commit()
        raise


async def import_flipkart_orders(db: Session, account: ChannelAccount) -> dict:
    """Import orders from Flipkart Seller API for the given channel account."""
    creds = get_provider_credentials(db, str(account.user_id), "flipkart")
    if not creds or not (creds.get("client_id") and creds.get("client_secret")):
        raise ValueError("Flipkart credentials missing. Add Seller ID, Client ID, and Client Secret in Integrations.")
    access_token = await flipkart_get_token(
        client_id=creds["client_id"],
        client_secret=creds["client_secret"],
    )
    from_d = datetime.now(timezone.utc) - timedelta(days=90)
    raw_items = await flipkart_get_orders(access_token=access_token, from_date=from_d)

    # Group by orderId so we create one Order per Flipkart order
    by_order: dict[str, list[dict]] = defaultdict(list)
    for item in raw_items:
        oid = item.get("orderId") or item.get("orderItemId") or str(id(item))
        by_order[oid].append(item)
    common_orders = []
    for order_id, items in by_order.items():
        if not items:
            continue
        first = items[0]
        total = sum(
            float(it.get("orderItemValue") or it.get("sellingPrice") or it.get("price") or 0) * int(it.get("quantity") or 1)
            for it in items
        )
        line_items = []
        for it in items:
            line_items.append({
                "sku": it.get("sellerSkuId") or it.get("skuId") or "",
                "title": it.get("productTitle") or it.get("title") or "Item",
                "quantity": int(it.get("quantity") or 1),
                "price": float(it.get("sellingPrice") or it.get("price") or 0),
            })
        common_orders.append({
            "id": order_id,
            "channel_order_id": order_id,
            "order_total": total,
            "customer_name": "Flipkart Customer",
            "customer_email": "",
            "payment_mode": "PREPAID",
            "items": line_items,
        })

    warehouse = get_default_warehouse(db)
    if not warehouse:
        raise Exception("No warehouse configured.")
    sync_job = SyncJob(
        channel_account_id=account.id,
        job_type=SyncJobType.PULL_ORDERS,
        status=SyncJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(sync_job)
    db.commit()
    db.refresh(sync_job)
    imported = skipped = errors = 0
    try:
        for common in common_orders:
            try:
                ok, msg = _persist_one_common_order(db, account, warehouse, common, sync_job)
                if ok:
                    imported += 1
                elif msg == "skipped":
                    skipped += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.ERROR, message=str(e), raw_payload=common))
                db.commit()
        sync_job.status = SyncJobStatus.SUCCESS
        sync_job.finished_at = datetime.now(timezone.utc)
        sync_job.records_processed = imported
        sync_job.records_failed = errors
        db.commit()
        return {"success": True, "imported": imported, "skipped": skipped, "errors": errors, "jobId": sync_job.id}
    except Exception as e:
        sync_job.status = SyncJobStatus.FAILED
        sync_job.finished_at = datetime.now(timezone.utc)
        sync_job.error_message = str(e)
        db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.ERROR, message=str(e)))
        db.commit()
        raise


async def import_myntra_orders(db: Session, account: ChannelAccount) -> dict:
    """Import orders from Myntra Partner API for the given channel account."""
    creds = get_provider_credentials(db, str(account.user_id), "myntra")
    if not creds or not creds.get("apiKey"):
        raise ValueError("Myntra credentials missing. Add Partner ID and API Key in Integrations.")
    from_d = datetime.now(timezone.utc) - timedelta(days=90)
    to_d = datetime.now(timezone.utc)
    raw_orders = await myntra_get_orders(
        api_key=creds["apiKey"],
        seller_id=(creds.get("seller_id") or account.seller_name or "").strip(),
        from_date=from_d,
        to_date=to_d,
    )
    common_orders = [normalize_myntra_order_to_common(o) for o in raw_orders]

    warehouse = get_default_warehouse(db)
    if not warehouse:
        raise Exception("No warehouse configured.")
    sync_job = SyncJob(
        channel_account_id=account.id,
        job_type=SyncJobType.PULL_ORDERS,
        status=SyncJobStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(sync_job)
    db.commit()
    db.refresh(sync_job)
    imported = skipped = errors = 0
    try:
        for common in common_orders:
            try:
                ok, msg = _persist_one_common_order(db, account, warehouse, common, sync_job)
                if ok:
                    imported += 1
                elif msg == "skipped":
                    skipped += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.ERROR, message=str(e), raw_payload=common))
                db.commit()
        sync_job.status = SyncJobStatus.SUCCESS
        sync_job.finished_at = datetime.now(timezone.utc)
        sync_job.records_processed = imported
        sync_job.records_failed = errors
        db.commit()
        return {"success": True, "imported": imported, "skipped": skipped, "errors": errors, "jobId": sync_job.id}
    except Exception as e:
        sync_job.status = SyncJobStatus.FAILED
        sync_job.finished_at = datetime.now(timezone.utc)
        sync_job.error_message = str(e)
        db.add(SyncLog(sync_job_id=sync_job.id, level=LogLevel.ERROR, message=str(e)))
        db.commit()
        raise
