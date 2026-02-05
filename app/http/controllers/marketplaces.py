"""
Marketplace-specific routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import ChannelAccount, User
from app.auth import get_current_user
from app.services.shopify import ShopifyService
from app.services.credentials import decrypt_token
import json

router = APIRouter()

@router.get("/shopify/shop")
async def get_shopify_shop(
    integration_id: int = Query(..., alias="integrationId"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get Shopify shop information"""
    account = db.query(ChannelAccount).filter(
        ChannelAccount.id == integration_id,
        ChannelAccount.user_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(
            status_code=404,
            detail="Integration not found"
        )
    
    try:
        decrypted_creds = decrypt_token(account.access_token or "")
        creds = json.loads(decrypted_creds) if isinstance(decrypted_creds, str) else decrypted_creds
        
        shop_domain = creds.get("shopDomain", "")
        access_token = creds.get("accessToken", "")
        
        if not shop_domain or not access_token:
            raise HTTPException(
                status_code=400,
                detail="Shop domain or access token not found"
            )
        
        service = ShopifyService()
        shop_info = await service.get_shop_info(shop_domain, access_token)
        
        return {
            "name": shop_info.get("name", ""),
            "domain": shop_info.get("domain", ""),
            "email": shop_info.get("email", ""),
            "currency": shop_info.get("currency", ""),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get shop info: {str(e)}"
        )
