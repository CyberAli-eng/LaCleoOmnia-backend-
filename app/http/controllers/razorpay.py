"""
Razorpay payment gateway integration controller
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import get_current_user
from app.services.razorpay_service import get_razorpay_service
from app.services.razorpay_sync import sync_razorpay_payments, sync_razorpay_settlements

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/payments")
async def get_razorpay_payments(
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get Razorpay payments for user
    """
    razorpay_service = get_razorpay_service()
    if not razorpay_service:
        return {"payments": [], "error": "Razorpay not configured"}
    
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        payments = await razorpay_service.fetch_payments(start_date, end_date)
        
        return {
            "payments": payments,
            "period": {
                "days": days,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
        }
        
    except Exception as e:
        logger.exception("Failed to fetch Razorpay payments: %s", e)
        return {"payments": [], "error": str(e)}


@router.get("/payments/{payment_id}")
async def get_razorpay_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get specific Razorpay payment
    """
    razorpay_service = get_razorpay_service()
    if not razorpay_service:
        return {"error": "Razorpay not configured"}
    
    try:
        payment = await razorpay_service.fetch_payment(payment_id)
        if not payment:
            return {"error": "Payment not found"}
        
        return {"payment": payment}
        
    except Exception as e:
        logger.exception("Failed to fetch Razorpay payment: %s", e)
        return {"error": str(e)}


@router.post("/sync/payments")
async def sync_razorpay_payments_endpoint(
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sync Razorpay payments and create order payment records
    """
    result = await sync_razorpay_payments(db, days_back=days, user_id=current_user.id)
    
    return {
        "message": f"Synced {result['synced']} Razorpay payments",
        "synced": result["synced"],
        "errors": result["errors"]
    }


@router.post("/sync/settlements")
async def sync_razorpay_settlements_endpoint(
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sync Razorpay settlements and create settlement records
    """
    result = await sync_razorpay_settlements(db, days_back=days, user_id=current_user.id)
        
        return {
            "message": f"Synced {result['synced']} Razorpay settlements",
            "synced": result["synced"],
            "errors": result["errors"]
        }


@router.post("/reconcile")
async def reconcile_razorpay_order(
    order_id: str,
    amount: float,
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually reconcile a Razorpay order payment
    """
    result = await reconcile_razorpay_order(
        db=db,
        order_id=order_id,
        amount=amount,
        transaction_id=transaction_id,
        user_id=current_user.id
    )
    
    return result


@router.post("/connect")
async def connect_razorpay(
    key_id: str,
    key_secret: str,
    webhook_secret: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Connect Razorpay payment gateway
    """
    # Validate required fields
    if not all([key_id, key_secret, webhook_secret]):
        raise HTTPException(status_code=400, detail="All fields are required")
    
    # TODO: Store credentials in database
    # For now, just validate the service works
    
    try:
        # Test service initialization
        from app.services.razorpay_service import RazorpayService
        test_service = RazorpayService(
            key_id=key_id,
            key_secret=key_secret,
            webhook_secret=webhook_secret
        )
        
        # Test fetching payments
        test_payments = await test_service.fetch_payments(
            datetime.now(timezone.utc) - timedelta(days=1),
            datetime.now(timezone.utc)
        )
        
        return {
            "status": "connected",
            "message": "Razorpay connected successfully",
            "test_payments": len(test_payments)
        }
        
    except Exception as e:
        logger.exception("Razorpay connection failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")


@router.get("/status")
async def get_razorpay_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get Razorpay connection status
    """
    razorpay_service = get_razorpay_service()
    
    if not razorpay_service:
        return {
            "connected": False,
            "message": "Razorpay not configured"
        }
    
    try:
        # Test service initialization
        test_service = RazorpayService(
            key_id=razorpay_service.key_id,
            key_secret=razorpay_service.key_secret,
            webhook_secret=razorpay_service.webhook_secret
        )
        
        # Test fetching payments
        test_payments = await test_service.fetch_payments(
            datetime.now(timezone.utc) - timedelta(days=1),
            datetime.now(timezone.utc)
        )
        
        return {
            "connected": True,
            "message": "Razorpay connected and working",
            "test_payments": len(test_payments)
        }
        
    except Exception as e:
        logger.exception("Razorpay status check failed: %s", e)
        return {
            "connected": False,
            "message": f"Status check failed: {str(e)}"
        }
