"""
Product routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Product, ProductVariant, User, UserRole
from app.auth import get_current_user, require_admin
from app.http.requests import ProductCreateRequest, VariantCreateRequest

router = APIRouter()

@router.get("")
async def list_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List products"""
    products = db.query(Product).all()
    result = []
    for product in products:
        variants = db.query(ProductVariant).filter(ProductVariant.product_id == product.id).all()
        result.append({
            "id": product.id,
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
            "status": product.status.value,
            "variants": [
                {
                    "id": v.id,
                    "sku": v.sku,
                    "barcode": v.barcode,
                    "mrp": float(v.mrp),
                    "sellingPrice": float(v.selling_price),
                    "status": v.status.value
                }
                for v in variants
            ]
        })
    return {"products": result}

@router.post("")
async def create_product(
    request: ProductCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create product (Admin only)"""
    product = Product(
        title=request.title,
        brand=request.brand,
        category=request.category
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"product": product}

@router.get("/{product_id}")
async def get_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"product": product}

@router.patch("/{product_id}")
async def update_product(
    product_id: str,
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update product (Admin only)"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if "title" in request:
        product.title = request["title"]
    if "brand" in request:
        product.brand = request["brand"]
    if "category" in request:
        product.category = request["category"]
    
    db.commit()
    db.refresh(product)
    return {"product": product}

@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete product (Admin only)"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    db.delete(product)
    db.commit()
    return {"ok": True}
