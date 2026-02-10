"""
Razorpay payment gateway integration for prepaid order settlement tracking
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.config import settings
from app.services.http_client import get_with_retry

logger = logging.getLogger(__name__)


class RazorpayService:
    """Razorpay API client for payment processing and settlement tracking"""
    
    def __init__(
        self,
        key_id: str,
        key_secret: str,
        webhook_secret: str,
        base_url: str = "https://api.razorpay.com"
    ):
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = webhook_secret
        self.base_url = base_url.rstrip("/")
        self.auth_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {self._get_auth_string()}"
        }
    
    def _get_auth_string(self) -> str:
        """Get base64 encoded auth string"""
        import base64
        auth_string = f"{self.key_id}:{self.key_secret}"
        return base64.b64encode(auth_string.encode()).decode()
    
    async def fetch_payments(self, from_date: datetime, to_date: datetime) -> List[Dict[str, Any]]:
        """Fetch Razorpay payments for date range"""
        try:
            url = f"{self.base_url}/v1/payments"
            params = {
                "from": from_date.strftime("%Y-%m-%d"),
                "to": to_date.strftime("%Y-%m-%d"),
                "count": 100
            }
            
            async with get_with_retry(url, params=params, headers=self.auth_headers, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.error("Razorpay payments API error: %s", response.status_code)
                    return []
                
                data = response.json()
                payments = data.get("items", [])
                
                # Normalize payment data
                normalized = []
                for payment in payments:
                    normalized.append({
                        "razorpay_payment_id": payment.get("id"),
                        "order_id": payment.get("description", "").split("#")[1].strip() if "#" in payment.get("description", "") else "",
                        "amount": float(payment.get("amount", 0)),
                        "currency": payment.get("currency", "INR"),
                        "status": payment.get("status"),
                        "method": payment.get("method"),
                        "created_at": payment.get("created_at"),
                        "captured_at": payment.get("captured_at"),
                        "fee": float(payment.get("fee", 0)),
                        "tax": float(payment.get("tax", 0)),
                        "entity": payment.get("entity", "order"),
                        "notes": payment.get("notes", "")
                    })
                
                return normalized
                
        except Exception as e:
            logger.error("Razorpay payments fetch failed: %s", e)
            return []
    
    async def fetch_settlements(self, from_date: datetime, to_date: datetime) -> List[Dict[str, Any]]:
        """Fetch Razorpay settlements for date range"""
        try:
            url = f"{self.base_url}/v1/settlements"
            params = {
                "from": from_date.strftime("%Y-%m-%d"),
                "to": to_date.strftime("%Y-%m-%d"),
                "count": 100
            }
            
            async with get_with_retry(url, params=params, headers=self.auth_headers, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.error("Razorpay settlements API error: %s", response.status_code)
                    return []
                
                data = response.json()
                settlements = data.get("items", [])
                
                # Normalize settlement data
                normalized = []
                for settlement in settlements:
                    normalized.append({
                        "razorpay_settlement_id": settlement.get("id"),
                        "order_id": settlement.get("description", "").split("#")[1].strip() if "#" in settlement.get("description", "") else "",
                        "amount": float(settlement.get("amount", 0)),
                        "currency": settlement.get("currency", "INR"),
                        "status": settlement.get("status"),
                        "fees": float(settlement.get("fees", 0)),
                        "tax": float(settlement.get("tax", 0)),
                        "utr": settlement.get("utr"),
                        "created_at": settlement.get("created_at"),
                        "processed_at": settlement.get("processed_at"),
                        "notes": settlement.get("notes", "")
                    })
                
                return normalized
                
        except Exception as e:
            logger.error("Razorpay settlements fetch failed: %s", e)
            return []
    
    async def fetch_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Fetch specific Razorpay payment"""
        try:
            url = f"{self.base_url}/v1/payments/{payment_id}"
            
            async with get_with_retry(url, headers=self.auth_headers, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.error("Razorpay payment API error: %s", response.status_code)
                    return None
                
                data = response.json()
                payment = data.get("item", {})
                
                # Normalize payment data
                normalized = {
                    "razorpay_payment_id": payment.get("id"),
                    "order_id": payment.get("description", "").split("#")[1].strip() if "#" in payment.get("description", "") else "",
                    "amount": float(payment.get("amount", 0)),
                    "currency": payment.get("currency", "INR"),
                    "status": payment.get("status"),
                    "method": payment.get("method"),
                    "created_at": payment.get("created_at"),
                    "captured_at": payment.get("captured_at"),
                    "fee": float(payment.get("fee", 0)),
                    "tax": float(payment.get("tax", 0)),
                    "entity": payment.get("entity", "order"),
                    "notes": payment.get("notes", ""),
                    "card": payment.get("card"),
                    "bank": payment.get("bank"),
                    "vpa": payment.get("vpa"),
                    "wallet": payment.get("wallet")
                }
                
                return normalized
                
        except Exception as e:
            logger.error("Razorpay payment fetch failed: %s", e)
            return None
    
    def verify_webhook_signature(self, payload: Dict[str, Any], signature: str) -> bool:
        """Verify Razorpay webhook signature"""
        try:
            import hmac
            import hashlib
            
            # Get webhook secret from environment
            webhook_secret = self.webhook_secret
            
            # Create signature string
            signature_string = f"{payload.get('payment_id', '')}|{payload.get('order_id', '')}|{payload.get('amount', '')}|{payload.get('currency', '')}|{payload.get('status', '')}|{payload.get('entity', '')}"
            
            # Generate expected signature
            expected_signature = hmac.new(
                webhook_secret.encode(),
                signature_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            return hmac.compare_digest(expected_signature, signature.encode())
            
        except Exception as e:
            logger.error("Webhook signature verification failed: %s", e)
            return False


def get_razorpay_service() -> RazorpayService:
    """Get Razorpay service instance"""
    key_id = getattr(settings, "RAZORPAY_KEY_ID", "")
    key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
    webhook_secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    
    if not all([key_id, key_secret, webhook_secret]):
        logger.warning("Razorpay credentials not configured")
        return None
    
    return RazorpayService(
        key_id=key_id,
        key_secret=key_secret,
        webhook_secret=webhook_secret
    )
