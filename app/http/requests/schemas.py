"""
Pydantic schemas for request/response validation (Http/Requests).
"""
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from app.models import (
    UserRole, ChannelType, ChannelAccountStatus, ProductStatus, VariantStatus,
    OrderStatus, PaymentMode, FulfillmentStatus, ShipmentStatus,
    SyncJobType, SyncJobStatus, LogLevel, InventoryMovementType
)

# Auth Schemas
class LoginRequest(BaseModel):
    email: str
    password: str

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v or len(v.split('@')) != 2:
            raise ValueError('Invalid email format')
        return v.lower().strip()

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v or len(v.split('@')) != 2:
            raise ValueError('Invalid email format')
        return v.lower().strip()

class LoginResponse(BaseModel):
    user: dict
    token: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole


class ForgotPasswordRequest(BaseModel):
    email: str

    @validator("email")
    def validate_email(cls, v):
        if "@" not in v or len(v.split("@")) != 2:
            raise ValueError("Invalid email format")
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


# Channel Schemas
class ShopifyConnectRequest(BaseModel):
    seller_name: str
    shop_domain: str
    access_token: str

class ChannelAccountResponse(BaseModel):
    id: str
    seller_name: str
    shop_domain: from typing import Optional
Optional[str]
    status: ChannelAccountStatus

# Order Schemas
class OrderItemResponse(BaseModel):
    id: str
    sku: str
    title: str
    qty: int
    price: Decimal
    fulfillment_status: FulfillmentStatus
    variant_id: from typing import Optional
Optional[str]

class OrderResponse(BaseModel):
    id: str
    channel_order_id: str
    customer_name: str
    customer_email: from typing import Optional
Optional[str]
    payment_mode: PaymentMode
    order_total: Decimal
    status: OrderStatus
    created_at: datetime
    items: List[OrderItemResponse]

class ShipOrderRequest(BaseModel):
    courier_name: str = "delhivery"
    awb_number: str
    tracking_url: from typing import Optional
Optional[str] = None
    label_url: from typing import Optional
Optional[str] = None
    forward_cost: float = 0.0
    reverse_cost: float = 0.0

# Inventory Schemas
class InventoryAdjustRequest(BaseModel):
    warehouse_id: str
    sku: str
    qty_delta: int
    reason: str

class InventoryResponse(BaseModel):
    id: str
    warehouse_id: str
    variant_id: str
    total_qty: int
    reserved_qty: int
    available_qty: int

# Product Schemas
class ProductCreateRequest(BaseModel):
    title: str
    brand: from typing import Optional
Optional[str] = None
    category: from typing import Optional
Optional[str] = None

class VariantCreateRequest(BaseModel):
    product_id: str
    sku: str
    barcode: from typing import Optional
Optional[str] = None
    mrp: Decimal
    selling_price: Decimal
    weight_grams: from typing import Optional
Optional[int] = None

# Warehouse Schemas
class WarehouseCreateRequest(BaseModel):
    name: str
    city: from typing import Optional
Optional[str] = None
    state: from typing import Optional
Optional[str] = None

# Sync Schemas
class SyncJobResponse(BaseModel):
    id: str
    job_type: SyncJobType
    status: SyncJobStatus
    started_at: from typing import Optional
Optional[datetime]
    finished_at: from typing import Optional
Optional[datetime]

class SyncLogResponse(BaseModel):
    id: str
    level: LogLevel
    message: str
    raw_payload: from typing import Optional
Optional[dict]
    created_at: datetime
