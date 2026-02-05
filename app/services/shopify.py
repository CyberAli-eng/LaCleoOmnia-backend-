"""
Shopify API service
"""
import httpx
import os
from app.models import ChannelAccount
from app.services.credentials import decrypt_token

class ShopifyService:
    def __init__(self, account: ChannelAccount = None):
        if account:
            self.account = account
            self.token = decrypt_token(account.access_token or "")
            self.shop = account.shop_domain or ""
        else:
            self.account = None
            self.token = None
            self.shop = None
        
        if self.shop:
            self.base_url = f"https://{self.shop}/admin/api/2024-01"
            self.headers = {
                "X-Shopify-Access-Token": self.token,
                "Content-Type": "application/json"
            }
    
    async def get_shop_info(self, shop_domain: str, access_token: str) -> dict:
        """Get shop information by domain and token"""
        # Handle both formats: "store.myshopify.com" or "store"
        if not shop_domain.endswith(".myshopify.com"):
            shop_domain = f"{shop_domain}.myshopify.com"
        base_url = f"https://{shop_domain}/admin/api/2024-01"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/shop.json",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("shop", {})
    
    async def ensure_webhook(self, shop_domain: str, access_token: str, app_secret: str, webhook_base_url: str):
        """Ensure all required webhooks are registered"""
        # Handle both formats: "store.myshopify.com" or "store"
        if not shop_domain.endswith(".myshopify.com"):
            shop_domain = f"{shop_domain}.myshopify.com"
        base_url = f"https://{shop_domain}/admin/api/2024-01"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }
        
        # All required webhooks as per requirements
        webhooks = [
            {
                "topic": "orders/create",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            },
            {
                "topic": "orders/updated",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            },
            {
                "topic": "orders/cancelled",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            },
            {
                "topic": "refunds/create",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            },
            {
                "topic": "fulfillments/create",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            },
            {
                "topic": "inventory_levels/update",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            },
            {
                "topic": "products/update",
                "address": f"{webhook_base_url}/api/webhooks/shopify",
                "format": "json"
            }
        ]
        
        async with httpx.AsyncClient() as client:
            # Get existing webhooks
            response = await client.get(
                f"{base_url}/webhooks.json",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            existing = response.json().get("webhooks", [])
            
            # Create a map of existing webhooks by topic
            existing_by_topic = {w.get("topic"): w for w in existing}
            registered = []
            errors = []
            
            # Register missing webhooks
            for webhook in webhooks:
                topic = webhook["topic"]
                existing_webhook = existing_by_topic.get(topic)
                
                # Check if webhook exists and points to our URL
                if existing_webhook and existing_webhook.get("address") == webhook["address"]:
                    registered.append({"topic": topic, "status": "exists"})
                    continue
                
                # Delete old webhook if it exists but points to different URL
                if existing_webhook:
                    try:
                        await client.delete(
                            f"{base_url}/webhooks/{existing_webhook['id']}.json",
                            headers=headers,
                            timeout=30.0
                        )
                    except:
                        pass  # Ignore delete errors
                
                # Register new webhook
                try:
                    response = await client.post(
                        f"{base_url}/webhooks.json",
                        headers=headers,
                        json={"webhook": webhook},
                        timeout=30.0
                    )
                    response.raise_for_status()
                    registered.append({"topic": topic, "status": "registered"})
                except Exception as e:
                    errors.append({"topic": topic, "error": str(e)})
            
            return {
                "registered": registered,
                "errors": errors,
                "total": len(webhooks)
            }
    
    async def get_shop(self) -> dict:
        """Get shop information (requires account initialization)"""
        if not self.account or not self.base_url:
            raise ValueError("ShopifyService must be initialized with account for this method")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/shop.json",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("shop", {})
    
    async def get_orders(self, limit: int = 250) -> list:
        """Get orders from Shopify"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/orders.json",
                params={
                    "status": "any",
                    "financial_status": "paid",
                    "fulfillment_status": "unfulfilled",
                    "limit": limit
                },
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("orders", [])
    
    async def get_products(self, limit: int = 250) -> list:
        """Get products from Shopify"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products.json",
                params={"limit": limit},
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("products", [])
    
    async def get_inventory_levels(self) -> list:
        """Get inventory levels from Shopify"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/inventory_levels.json",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("inventory_levels", [])
    
    async def update_inventory_level(self, inventory_item_id: int, location_id: int, quantity: int):
        """Update inventory level in Shopify"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/inventory_levels/set.json",
                json={
                    "location_id": location_id,
                    "inventory_item_id": inventory_item_id,
                    "available": quantity
                },
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_locations(self) -> list:
        """Get locations from Shopify"""
        if not self.account or not self.base_url:
            raise ValueError("ShopifyService must be initialized with account for this method")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/locations.json",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("locations", [])
    
    async def get_products_count(self) -> int:
        """Get total products count from Shopify"""
        if not self.account or not self.base_url:
            raise ValueError("ShopifyService must be initialized with account for this method")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/products/count.json",
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("count", 0)
    
    async def get_recent_orders(self, limit: int = 10) -> list:
        """Get recent orders from Shopify"""
        if not self.account or not self.base_url:
            raise ValueError("ShopifyService must be initialized with account for this method")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/orders.json",
                params={
                    "status": "any",
                    "limit": limit,
                    "order": "created_at desc"
                },
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data.get("orders", [])
