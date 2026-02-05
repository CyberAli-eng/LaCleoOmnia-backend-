"""
SQLAlchemy models matching the Prisma schema.
All model and enum definitions live here for simplicity and to avoid circular imports.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date, ForeignKey, Numeric, Enum as SQLEnum, JSON, UniqueConstraint
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from app.database import Base
import enum
import uuid

# Enums
class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"

class ChannelType(str, enum.Enum):
    SHOPIFY = "SHOPIFY"
    AMAZON = "AMAZON"
    FLIPKART = "FLIPKART"
    MYNTRA = "MYNTRA"

class ChannelAccountStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"

class ProductStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class VariantStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class InventoryMovementType(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"

class OrderStatus(str, enum.Enum):
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"
    HOLD = "HOLD"

class PaymentMode(str, enum.Enum):
    PREPAID = "PREPAID"
    COD = "COD"

class FulfillmentStatus(str, enum.Enum):
    PENDING = "PENDING"
    MAPPED = "MAPPED"
    UNMAPPED_SKU = "UNMAPPED_SKU"

class ShipmentStatus(str, enum.Enum):
    CREATED = "CREATED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    RTO_INITIATED = "RTO_INITIATED"
    RTO_DONE = "RTO_DONE"
    IN_TRANSIT = "IN_TRANSIT"
    LOST = "LOST"

class SyncJobType(str, enum.Enum):
    PULL_ORDERS = "PULL_ORDERS"
    PULL_PRODUCTS = "PULL_PRODUCTS"
    PUSH_INVENTORY = "PUSH_INVENTORY"

class SyncJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class LogLevel(str, enum.Enum):
    INFO = "INFO"
    ERROR = "ERROR"

# Models
class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column("password_hash", String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.STAFF)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())
    password_reset_token = Column("password_reset_token", String, nullable=True)
    password_reset_expires = Column("password_reset_expires", DateTime(timezone=True), nullable=True)

class Channel(Base):
    __tablename__ = "channels"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(SQLEnum(ChannelType), unique=True, nullable=False)
    is_active = Column("is_active", Boolean, default=True)
    created_at = Column("created_at", DateTime, server_default=func.now())

    accounts = relationship("ChannelAccount", back_populates="channel")
    orders = relationship("Order", back_populates="channel")

class ChannelAccount(Base):
    __tablename__ = "channel_accounts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id = Column("channel_id", String, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    user_id = Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seller_name = Column("seller_name", String, nullable=False)
    shop_domain = Column("shop_domain", String, nullable=True)
    access_token = Column("access_token", String, nullable=True)  # Encrypted
    status = Column(SQLEnum(ChannelAccountStatus), default=ChannelAccountStatus.DISCONNECTED)
    created_at = Column("created_at", DateTime, server_default=func.now())

    channel = relationship("Channel", back_populates="accounts")
    orders = relationship("Order", back_populates="channel_account")
    sync_jobs = relationship("SyncJob", back_populates="channel_account")

class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    brand = Column(String, nullable=True)
    category = Column(String, nullable=True)
    status = Column(SQLEnum(ProductStatus), default=ProductStatus.ACTIVE)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    variants = relationship("ProductVariant", back_populates="product")

class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column("product_id", String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    sku = Column(String, unique=True, nullable=False, index=True)
    barcode = Column(String, nullable=True)
    mrp = Column("mrp", Numeric(10, 2), nullable=False)
    selling_price = Column("selling_price", Numeric(10, 2), nullable=False)
    weight_grams = Column("weight_grams", Integer, nullable=True)
    status = Column(SQLEnum(VariantStatus), default=VariantStatus.ACTIVE)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    product = relationship("Product", back_populates="variants")
    inventory = relationship("Inventory", back_populates="variant")
    inventory_movements = relationship("InventoryMovement", back_populates="variant")
    order_items = relationship("OrderItem", back_populates="variant")

class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())

    inventory = relationship("Inventory", back_populates="warehouse")
    inventory_movements = relationship("InventoryMovement", back_populates="warehouse")

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column("warehouse_id", String, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column("variant_id", String, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False)
    total_qty = Column("total_qty", Integer, default=0)
    reserved_qty = Column("reserved_qty", Integer, default=0)
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    warehouse = relationship("Warehouse", back_populates="inventory")
    variant = relationship("ProductVariant", back_populates="inventory")

    __table_args__ = (
        UniqueConstraint("warehouse_id", "variant_id", name="inventory_warehouse_variant_unique"),
    )

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column("warehouse_id", String, ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column("variant_id", String, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False)
    type = Column(SQLEnum(InventoryMovementType), nullable=False)
    qty = Column(Integer, nullable=False)
    reference = Column(String, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())

    warehouse = relationship("Warehouse", back_populates="inventory_movements")
    variant = relationship("ProductVariant", back_populates="inventory_movements")

class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id = Column("channel_id", String, ForeignKey("channels.id", ondelete="SET NULL"), nullable=True)
    channel_account_id = Column("channel_account_id", String, ForeignKey("channel_accounts.id", ondelete="SET NULL"), nullable=True)
    channel_order_id = Column("channel_order_id", String, nullable=False)
    customer_name = Column("customer_name", String, nullable=False)
    customer_email = Column("customer_email", String, nullable=True)
    shipping_address = Column("shipping_address", String, nullable=True)
    billing_address = Column("billing_address", String, nullable=True)
    payment_mode = Column("payment_mode", SQLEnum(PaymentMode), nullable=False)
    order_total = Column("order_total", Numeric(10, 2), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.NEW)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    channel = relationship("Channel", back_populates="orders")
    channel_account = relationship("ChannelAccount", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    shipment = relationship("Shipment", back_populates="order", uselist=False)

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "channel_account_id",
            "channel_order_id",
            name="orders_channel_account_order_unique",
        ),
    )

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column("order_id", String, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column("variant_id", String, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    sku = Column(String, nullable=False)
    title = Column(String, nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column("price", Numeric(10, 2), nullable=False)
    fulfillment_status = Column("fulfillment_status", SQLEnum(FulfillmentStatus), default=FulfillmentStatus.PENDING)

    order = relationship("Order", back_populates="items")
    variant = relationship("ProductVariant", back_populates="order_items")

class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column("order_id", String, ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False)
    courier_name = Column("courier_name", String, nullable=False)
    awb_number = Column("awb_number", String, nullable=False)
    tracking_url = Column("tracking_url", String, nullable=True)
    label_url = Column("label_url", String, nullable=True)
    status = Column(SQLEnum(ShipmentStatus), default=ShipmentStatus.CREATED)
    shipped_at = Column("shipped_at", DateTime, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())
    forward_cost = Column("forward_cost", Numeric(12, 2), default=0, nullable=False)
    reverse_cost = Column("reverse_cost", Numeric(12, 2), default=0, nullable=False)
    last_synced_at = Column("last_synced_at", DateTime, nullable=True)

    order = relationship("Order", back_populates="shipment")

class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_account_id = Column("channel_account_id", String, ForeignKey("channel_accounts.id", ondelete="CASCADE"), nullable=False)
    job_type = Column("job_type", SQLEnum(SyncJobType), nullable=False)
    status = Column(SQLEnum(SyncJobStatus), default=SyncJobStatus.QUEUED)
    started_at = Column("started_at", DateTime, nullable=True)
    finished_at = Column("finished_at", DateTime, nullable=True)
    records_processed = Column("records_processed", Integer, default=0)
    records_failed = Column("records_failed", Integer, default=0)
    error_message = Column("error_message", String, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())

    channel_account = relationship("ChannelAccount", back_populates="sync_jobs")
    logs = relationship("SyncLog", back_populates="sync_job", cascade="all, delete-orphan")

class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sync_job_id = Column("sync_job_id", String, ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False)
    level = Column(SQLEnum(LogLevel), nullable=False)
    message = Column(String, nullable=False)
    raw_payload = Column("raw_payload", JSON, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())

    sync_job = relationship("SyncJob", back_populates="logs")

class LabelStatus(str, enum.Enum):
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    PRINTED = "PRINTED"
    CANCELLED = "CANCELLED"

class Label(Base):
    __tablename__ = "labels"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column("order_id", String, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tracking_number = Column("tracking_number", String, nullable=False)
    carrier = Column(String, nullable=False)
    status = Column(String, default="PENDING")
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    order = relationship("Order")
    user = relationship("User")

class AuditLogAction(str, enum.Enum):
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_PACKED = "ORDER_PACKED"
    ORDER_SHIPPED = "ORDER_SHIPPED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    INVENTORY_ADJUSTED = "INVENTORY_ADJUSTED"
    SHIPMENT_CREATED = "SHIPMENT_CREATED"
    INTEGRATION_CONNECTED = "INTEGRATION_CONNECTED"
    INTEGRATION_DISCONNECTED = "INTEGRATION_DISCONNECTED"

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column("user_id", String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(SQLEnum(AuditLogAction), nullable=False)
    entity_type = Column("entity_type", String, nullable=False)
    entity_id = Column("entity_id", String, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())

    user = relationship("User")


class ShopifyIntegration(Base):
    __tablename__ = "shopify_integrations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    shop_domain = Column("shop_domain", String, unique=True, nullable=False, index=True)
    access_token = Column("access_token", String, nullable=False)
    scopes = Column("scopes", String, nullable=True)
    app_secret_encrypted = Column("app_secret_encrypted", String, nullable=True)
    installed_at = Column("installed_at", DateTime, server_default=func.now())
    last_synced_at = Column("last_synced_at", DateTime, nullable=True)


class ShopifyInventory(Base):
    __tablename__ = "shopify_inventory"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    shop_domain = Column("shop_domain", String, nullable=False, index=True)
    sku = Column("sku", String, nullable=False, index=True)
    product_name = Column("product_name", String, nullable=True)
    variant_id = Column("variant_id", String, nullable=True)
    inventory_item_id = Column("inventory_item_id", String, nullable=True)
    location_id = Column("location_id", String, nullable=True)
    available = Column("available", Integer, default=0)
    synced_at = Column("synced_at", DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("shop_domain", "sku", "location_id", name="shopify_inventory_shop_sku_loc_unique"),)


class SkuCost(Base):
    __tablename__ = "sku_costs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sku = Column("sku", String, unique=True, nullable=False, index=True)
    product_cost = Column("product_cost", Numeric(12, 2), default=0, nullable=False)
    packaging_cost = Column("packaging_cost", Numeric(12, 2), default=0, nullable=False)
    box_cost = Column("box_cost", Numeric(12, 2), default=0, nullable=False)
    inbound_cost = Column("inbound_cost", Numeric(12, 2), default=0, nullable=False)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())


class OrderProfit(Base):
    __tablename__ = "order_profit"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column("order_id", String, ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False)
    revenue = Column("revenue", Numeric(12, 2), default=0, nullable=False)
    product_cost = Column("product_cost", Numeric(12, 2), default=0, nullable=False)
    packaging_cost = Column("packaging_cost", Numeric(12, 2), default=0, nullable=False)
    shipping_cost = Column("shipping_cost", Numeric(12, 2), default=0, nullable=False)
    shipping_forward = Column("shipping_forward", Numeric(12, 2), default=0, nullable=False)
    shipping_reverse = Column("shipping_reverse", Numeric(12, 2), default=0, nullable=False)
    marketing_cost = Column("marketing_cost", Numeric(12, 2), default=0, nullable=False)
    payment_fee = Column("payment_fee", Numeric(12, 2), default=0, nullable=False)
    net_profit = Column("net_profit", Numeric(12, 2), default=0, nullable=False)
    rto_loss = Column("rto_loss", Numeric(12, 2), default=0, nullable=False)
    lost_loss = Column("lost_loss", Numeric(12, 2), default=0, nullable=False)
    courier_status = Column("courier_status", String, nullable=True)
    final_status = Column("final_status", String, nullable=True)
    status = Column("status", String, default="computed", nullable=False)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    order = relationship("Order", backref=backref("profit", uselist=False))


class ShipmentTracking(Base):
    __tablename__ = "shipment_tracking"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    shipment_id = Column("shipment_id", String, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    waybill = Column("waybill", String, nullable=False, index=True)
    status = Column("status", String, nullable=True)
    delivery_status = Column("delivery_status", String, nullable=True)
    rto_status = Column("rto_status", String, nullable=True)
    raw_response = Column("raw_response", JSON, nullable=True)
    last_updated_at = Column("last_updated_at", DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column("created_at", DateTime, server_default=func.now())

    shipment = relationship("Shipment", backref=backref("tracking", uselist=False))


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column("user_id", String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column("provider_id", String, nullable=False, index=True)
    value_encrypted = Column("value_encrypted", String, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())
    updated_at = Column("updated_at", DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "provider_id", name="uq_provider_credentials_user_provider"),)
    user = relationship("User")


class AdSpendDaily(Base):
    __tablename__ = "ad_spend_daily"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    date = Column("date", Date, nullable=False, index=True)
    platform = Column("platform", String, nullable=False, index=True)
    spend = Column("spend", Numeric(12, 2), default=0, nullable=False)
    currency = Column("currency", String(3), default="INR", nullable=False)
    synced_at = Column("synced_at", DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("date", "platform", name="uq_ad_spend_daily_date_platform"),)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source = Column("source", String, nullable=False, index=True)
    shop_domain = Column("shop_domain", String, nullable=True, index=True)
    topic = Column("topic", String, nullable=False, index=True)
    payload_summary = Column("payload_summary", String, nullable=True)
    processed_at = Column("processed_at", DateTime, nullable=True)
    error = Column("error", String, nullable=True)
    created_at = Column("created_at", DateTime, server_default=func.now())
