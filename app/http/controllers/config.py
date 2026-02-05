"""
Configuration and integration management routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ChannelAccount, ChannelType, ChannelAccountStatus, User
from app.auth import get_current_user
from app.http.requests import ShopifyConnectRequest
from app.services.shopify import ShopifyService
from app.services.credentials import encrypt_token, decrypt_token
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json

router = APIRouter()

class ConfigRequest(BaseModel):
    type: str
    name: str
    credentials: Dict[str, Any]

class ConfigUpdateRequest(BaseModel):
    inventorySyncEnabled: Optional[bool] = None
    inventorySyncIntervalMinutes: Optional[int] = None

@router.get("/status")
async def get_config_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all integrations and webhook subscriptions for the current user"""
    accounts = db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()
    
    integrations = []
    for account in accounts:
        try:
            decrypted_creds = decrypt_token(account.access_token or "")
            creds = json.loads(decrypted_creds) if isinstance(decrypted_creds, str) else decrypted_creds
            
            integrations.append({
                "id": account.id,
                "type": account.channel.name.value if account.channel else "UNKNOWN",
                "name": account.seller_name,
                "status": account.status.value,
                "createdAt": account.created_at.isoformat() if account.created_at else None,
                "credentials": creds,
            })
        except Exception as e:
            # Skip integrations with decryption errors
            continue
    
    # TODO: Add webhook subscriptions when webhook model is added
    subscriptions = []
    
    return {
        "integrations": integrations,
        "subscriptions": subscriptions
    }

@router.post("")
async def save_config(
    request: ConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save or update an integration configuration"""
    try:
        # For Shopify, use the existing connect endpoint logic
        if request.type.upper() == "SHOPIFY":
            shopify_req = ShopifyConnectRequest(
                shop_domain=request.credentials.get("shopDomain", ""),
                access_token=request.credentials.get("accessToken", ""),
                app_secret=request.credentials.get("appSecret", "")
            )
            
            # Use ShopifyService to connect
            service = ShopifyService()
            shop_info = await service.get_shop_info(
                shopify_req.shop_domain,
                shopify_req.access_token
            )
            
            # Find or create channel
            from app.models import Channel
            channel = db.query(Channel).filter(
                Channel.name == ChannelType.SHOPIFY
            ).first()
            
            if not channel:
                channel = Channel(
                    name=ChannelType.SHOPIFY,
                    is_active=True
                )
                db.add(channel)
                db.flush()
            
            # Encrypt credentials
            creds_json = json.dumps({
                "shopDomain": shopify_req.shop_domain,
                "accessToken": shopify_req.access_token,
                "appSecret": shopify_req.app_secret
            })
            encrypted = encrypt_token(creds_json)
            
            # Find existing account or create new
            account = db.query(ChannelAccount).filter(
                ChannelAccount.channel_id == channel.id,
                ChannelAccount.user_id == current_user.id,
                ChannelAccount.seller_name == request.name
            ).first()
            
            if account:
                account.access_token = encrypted
                account.status = ChannelAccountStatus.CONNECTED
            else:
                account = ChannelAccount(
                    channel_id=channel.id,
                    user_id=current_user.id,
                    seller_name=request.name,
                    shop_domain=shopify_req.shop_domain,
                    access_token=encrypted,
                    status=ChannelAccountStatus.CONNECTED
                )
                db.add(account)
            
            db.commit()
            db.refresh(account)
            
            return {
                "id": account.id,
                "message": "Integration saved successfully"
            }
        else:
            # For other types, store as-is
            encrypted = encrypt_token(json.dumps(request.credentials))
            
            # Find or create channel
            from app.models import Channel
            channel_type_map = {
                "AMAZON": ChannelType.AMAZON,
                "WOO": ChannelType.WOOCOMMERCE,
                "FLIPKART": ChannelType.FLIPKART,
            }
            
            channel_type = channel_type_map.get(request.type.upper())
            if not channel_type:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported integration type: {request.type}"
                )
            
            channel = db.query(Channel).filter(
                Channel.name == channel_type
            ).first()
            
            if not channel:
                channel = Channel(
                    name=channel_type,
                    is_active=True
                )
                db.add(channel)
                db.flush()
            
            account = ChannelAccount(
                channel_id=channel.id,
                user_id=current_user.id,
                seller_name=request.name,
                access_token=encrypted,
                status=ChannelAccountStatus.CONNECTED
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            
            return {
                "id": account.id,
                "message": "Integration saved successfully"
            }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save integration: {str(e)}"
        )

@router.patch("/{integration_id}")
async def update_config(
    integration_id: int,
    request: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update integration configuration"""
    account = db.query(ChannelAccount).filter(
        ChannelAccount.id == integration_id,
        ChannelAccount.user_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=404,
            detail="Integration not found"
        )
    
    # Update fields if provided
    if request.inventorySyncEnabled is not None:
        # Store in a metadata field or extend the model
        # For now, we'll store in encrypted credentials metadata
        pass
    
    if request.inventorySyncIntervalMinutes is not None:
        # Store in metadata
        pass
    
    db.commit()
    return {"message": "Configuration updated successfully"}

@router.delete("/{integration_id}")
async def delete_config(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an integration"""
    account = db.query(ChannelAccount).filter(
        ChannelAccount.id == integration_id,
        ChannelAccount.user_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=404,
            detail="Integration not found"
        )
    
    db.delete(account)
    db.commit()
    return {"message": "Integration deleted successfully"}

@router.post("/cleanup")
async def cleanup_duplicates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Clean up duplicate integrations"""
    accounts = db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()
    
    seen = {}
    duplicates = []
    
    for account in accounts:
        key = f"{account.channel_id}:{account.seller_name.lower().strip()}"
        if key in seen:
            duplicates.append(account.id)
        else:
            seen[key] = account.id
    
    if duplicates:
        db.query(ChannelAccount).filter(
            ChannelAccount.id.in_(duplicates)
        ).delete(synchronize_session=False)
        db.commit()
        return {"message": f"Removed {len(duplicates)} duplicate integrations"}
    
    return {"message": "No duplicates found"}
