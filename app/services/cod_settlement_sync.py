"""
COD settlement synchronization service for Selloship and Delhivery remittance tracking
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.config import settings
from app.services.selloship_service import get_selloship_client
from app.services.delhivery_service import get_client as get_delhivery_client
from app.services.http_client import get_with_retry

logger = logging.getLogger(__name__)


class CODSettlementProvider:
    """Base class for COD settlement providers"""
    
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
    
    async def fetch_remittances(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Fetch remittance data for date range"""
        raise NotImplementedError("Subclasses must implement fetch_remittances")
    
    async def fetch_settlement_file(self, file_url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse settlement file"""
        try:
            async with get_with_retry(file_url, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.warning("Failed to fetch settlement file: %s", response.status_code)
                    return None
                
                content = response.text
                if not content:
                    return None
                
                # Parse CSV/Excel format (implement basic CSV parsing)
                lines = content.strip().split('\n')
                if len(lines) < 2:
                    return None
                
                headers = [h.strip().lower() for h in lines[0].split(',')]
                data = []
                
                for line in lines[1:]:
                    values = line.strip().split(',')
                    if len(values) != len(headers):
                        continue
                    
                    row = dict(zip(headers, values))
                    # Clean and convert data
                    clean_row = {}
                    for key, value in row.items():
                        clean_key = key.strip().lower().replace(' ', '_')
                        clean_value = value.strip()
                        
                        # Convert numeric values
                        if clean_key in ['amount', 'cod_amount', 'shipping_charge']:
                            try:
                                clean_value = float(clean_value)
                            except:
                                clean_value = 0.0
                        
                        clean_row[clean_key] = clean_value
                    
                    data.append(clean_row)
                
                return {
                    "provider": self.name,
                    "data": data,
                    "period": {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat()
                    }
                }
        except Exception as e:
            logger.error("Failed to parse settlement file: %s", e)
            return None


class SelloshipCODSettlement(CODSettlementProvider):
    """Selloship COD settlement implementation"""
    
    def __init__(self):
        super().__init__(
            name="Selloship",
            base_url=getattr(settings, "SELLOSHIP_BASE_URL", "https://selloship.com/api/lock_actvs/channels")
        )
        self.auth_headers = {}
    
    async def _get_auth_headers(self) -> Dict[str, str]:
        """Get Selloship auth headers"""
        if not self.auth_headers:
            # Use token from env or get fresh token
            api_key = getattr(settings, "SELLOSHIP_API_KEY", None)
            if api_key:
                self.auth_headers = {"Authorization": f"token {api_key.strip()}"}
            else:
                # Get token via auth endpoint
                from app.services.selloship_service import fetch_selloship_token
                username = getattr(settings, "SELLOSHIP_USERNAME", "")
                password = getattr(settings, "SELLOSHIP_PASSWORD", "")
                
                if username and password:
                    token = await fetch_selloship_token(username, password)
                    if token:
                        self.auth_headers = {"Authorization": f"token {token}"}
                        logger.info("Selloship token refreshed")
        
        return self.auth_headers
    
    async def fetch_remittances(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Fetch Selloship COD remittances"""
        headers = await self._get_auth_headers()
        if not headers:
            logger.warning("No Selloship auth available for COD settlements")
            return []
        
        try:
            # Selloship COD remittance endpoint
            url = f"{self.base_url}/cod/remittances"
            params = {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            }
            
            async with get_with_retry(url, params=params, headers=headers, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.warning("Selloship COD remittances API error: %s", response.status_code)
                    return []
                
                data = response.json()
                remittances = data.get("remittances", [])
                
                # Normalize remittance data
                normalized = []
                for rem in remittances:
                    normalized.append({
                        "awb": rem.get("awb"),
                        "order_id": rem.get("order_id"),
                        "cod_amount": float(rem.get("cod_amount", 0)),
                        "shipping_charge": float(rem.get("shipping_charge", 0)),
                        "remittance_date": rem.get("remittance_date"),
                        "status": rem.get("status", "PENDING"),
                        "utr": rem.get("utr")
                    })
                
                return normalized
                
        except Exception as e:
            logger.error("Selloship COD remittances fetch failed: %s", e)
            return []


class DelhiveryCODSettlement(CODSettlementProvider):
    """Delhivery COD settlement implementation"""
    
    def __init__(self):
        super().__init__(
            name="Delhivery",
            base_url=getattr(settings, "DELHIVERY_BASE_URL", "https://track.delhivery.com")
        )
        self.auth_headers = {"Authorization": f"Token {getattr(settings, 'DELHIVERY_API_KEY', '')}"}
    
    async def fetch_remittances(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Fetch Delhivery COD remittances"""
        try:
            # Delhivery COD reports endpoint
            url = f"{self.base_url}/api/cod/reports"
            params = {
                "from": start_date.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d"),
                "format": "json"
            }
            
            async with get_with_retry(url, params=params, headers=self.auth_headers, timeout=30.0) as response:
                if response.status_code != 200:
                    logger.warning("Delhivery COD reports API error: %s", response.status_code)
                    return []
                
                data = response.json()
                reports = data.get("reports", [])
                
                # Normalize Delhivery COD data
                normalized = []
                for report in reports:
                    normalized.append({
                        "awb": report.get("waybill"),
                        "order_id": report.get("order_id"),
                        "cod_amount": float(report.get("cod_amount", 0)),
                        "shipping_charge": float(report.get("shipping_charge", 0)),
                        "remittance_date": report.get("remittance_date"),
                        "status": report.get("remittance_status", "PENDING"),
                        "utr": report.get("utr_number")
                    })
                
                return normalized
                
        except Exception as e:
            logger.error("Delhivery COD reports fetch failed: %s", e)
            return []


def get_cod_settlement_provider(provider_name: str) -> CODSettlementProvider:
    """Get COD settlement provider instance"""
    if provider_name.lower() == "selloship":
        return SelloshipCODSettlement()
    elif provider_name.lower() == "delhivery":
        return DelhiveryCODSettlement()
    else:
        raise ValueError(f"Unsupported COD settlement provider: {provider_name}")


def sync_cod_settlements(
    db: Any,
    days_back: int = 7,
    providers: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sync COD settlements from configured providers
    """
    if not providers:
        providers = ["selloship", "delhivery"]  # Default to both
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)
    
    results = {}
    total_synced = 0
    total_errors = []
    
    for provider_name in providers:
        try:
            provider = get_cod_settlement_provider(provider_name)
            remittances = await provider.fetch_remittances(start_date, end_date)
            
            # Store remittances in database
            stored_count = 0
            for remittance in remittances:
                try:
                    # Check if order exists
                    from app.models import Order, OrderFinance, OrderStatus
                    
                    order = db.query(Order).filter(
                        Order.channel_order_id == remittance["order_id"]
                    ).first()
                    
                    if order:
                        # Update COD settlement info
                        order_finance = db.query(OrderFinance).filter(
                            OrderFinance.order_id == order.id
                        ).first()
                        
                        if not order_finance:
                            order_finance = OrderFinance(
                                order_id=order.id,
                                partner="COD",
                                settlement_status="PENDING",
                                cod_amount=Decimal(str(remittance["cod_amount"])),
                                settlement_amount=Decimal(str(remittance["cod_amount"])),
                                settlement_date=datetime.fromisoformat(remittance["remittance_date"]) if remittance["remittance_date"] else None,
                                utr=remittance["utr"],
                                raw_response=remittance
                            )
                            db.add(order_finance)
                        else:
                            # Update existing record
                            order_finance.partner = "COD"
                            order_finance.settlement_status = "PENDING"
                            order_finance.cod_amount = Decimal(str(remittance["cod_amount"]))
                            order_finance.settlement_amount = Decimal(str(remittance["cod_amount"]))
                            order_finance.settlement_date = datetime.fromisoformat(remittance["remittance_date"]) if remittance["remittance_date"] else order_finance.settlement_date
                            order_finance.utr = remittance["utr"]
                            order_finance.raw_response = remittance
                            order_finance.updated_at = datetime.now(timezone.utc)
                        
                        # Update order status
                        if remittance["status"].upper() in ["SETTLED", "CREDITED"]:
                            order.status = OrderStatus.DELIVERED
                        elif remittance["status"].upper() in ["FAILED", "REJECTED"]:
                            order.status = OrderStatus.RTO_INITIATED
                        else:
                            order.status = OrderStatus.DELIVERED
                        
                        order.updated_at = datetime.now(timezone.utc)
                        stored_count += 1
                
                db.commit()
                except Exception as e:
                    logger.error("Failed to store COD remittance %s: %s", e)
                    total_errors.append(f"{provider_name}: {str(e)}")
            
            total_synced += stored_count
            results[provider_name] = {
                "synced": stored_count,
                "errors": len([e for e in total_errors if provider_name in e])
            }
    
    return {
        "providers": results,
        "total_synced": total_synced,
        "total_errors": total_errors,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    }
