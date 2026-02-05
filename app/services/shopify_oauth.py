"""
Shopify OAuth service - Production-grade implementation
"""
import httpx
import hmac
import hashlib
import secrets
import time
from urllib.parse import urlencode, parse_qs, urlparse, quote_plus
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class ShopifyOAuthService:
    """Handle Shopify OAuth flow. Uses provided api_key/api_secret or falls back to settings (env)."""
    
    def __init__(self, api_key: str | None = None, api_secret: str | None = None, scopes: str | None = None):
        self.api_key = (api_key or "").strip() or getattr(settings, "SHOPIFY_API_KEY", "") or ""
        self.api_secret = (api_secret or "").strip() or getattr(settings, "SHOPIFY_API_SECRET", "") or ""
        self.scopes = (scopes or "").strip() or getattr(settings, "SHOPIFY_SCOPES", "") or ""
    
    def normalize_shop_domain(self, shop_domain: str) -> str:
        """Normalize and validate shop domain"""
        if not shop_domain:
            raise ValueError("Shop domain is required")
        
        shop = shop_domain.lower().strip()
        
        # Remove protocol if present
        shop = shop.replace("https://", "").replace("http://", "")
        
        # Remove trailing slash
        shop = shop.rstrip("/")
        
        # Ensure .myshopify.com suffix
        if not shop.endswith(".myshopify.com"):
            # If it's just the shop name, add .myshopify.com
            if "." not in shop:
                shop = f"{shop}.myshopify.com"
            else:
                raise ValueError(f"Invalid shop domain format: {shop_domain}. Must be 'shopname' or 'shopname.myshopify.com'")
        
        # Validate format
        if not shop.count(".") >= 2 or len(shop) < 10:
            raise ValueError(f"Invalid shop domain: {shop_domain}")
        
        return shop
    
    def get_install_url(self, shop_domain: str, redirect_uri: str, state: str = None) -> str:
        """Generate Shopify OAuth install URL - CORRECT FORMAT: /admin/oauth/authorize"""
        try:
            shop = self.normalize_shop_domain(shop_domain)
            
            # Validate redirect_uri
            parsed_redirect = urlparse(redirect_uri)
            if not parsed_redirect.scheme or not parsed_redirect.netloc:
                raise ValueError(f"Invalid redirect_uri: {redirect_uri}")
            
            params = {
                "client_id": self.api_key,
                "scope": self.scopes,
                "redirect_uri": redirect_uri,
            }
            
            # Add state parameter if provided
            if state:
                params["state"] = state
            
            # CORRECT OAuth URL format: https://{shop}/admin/oauth/authorize
            oauth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"
            
            logger.info(f"Generated OAuth install URL for shop: {shop} (redirect_uri: {redirect_uri[:50]}...)")
            return oauth_url
            
        except Exception as e:
            logger.error(f"Failed to generate OAuth install URL: {e}")
            raise
    
    def verify_hmac(self, query_string: str) -> bool:
        """Verify HMAC signature from Shopify callback - EXACT implementation per Shopify docs"""
        if not query_string or not self.api_secret:
            logger.warning("HMAC verification skipped: missing query_string or api_secret")
            return False
        
        try:
            # Parse query string
            params = parse_qs(query_string, keep_blank_values=True)
            hmac_param = params.get("hmac", [None])[0]
            
            if not hmac_param:
                logger.warning("HMAC verification failed: no hmac parameter in query string")
                return False
            
            # Remove hmac and signature from params (as per Shopify docs)
            params.pop("hmac", None)
            params.pop("signature", None)
            
            # Rebuild query string exactly as Shopify expects
            # Sort parameters alphabetically by key
            sorted_params = sorted(params.items())
            query_parts = []
            for key, values in sorted_params:
                # Handle multiple values for same key
                for value in values:
                    # URL encode the value
                    encoded_value = quote_plus(str(value)) if value else ""
                    query_parts.append(f"{key}={encoded_value}")
            
            message = "&".join(query_parts)
            
            # Calculate HMAC using SHA256
            calculated_hmac = hmac.new(
                self.api_secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            
            # Use constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(calculated_hmac, hmac_param)
            
            if not is_valid:
                logger.warning(f"HMAC verification failed: calculated={calculated_hmac[:10]}..., received={hmac_param[:10]}...")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False
    
    async def exchange_code_for_token(self, shop_domain: str, code: str) -> dict:
        """Exchange authorization code for access token"""
        try:
            shop = self.normalize_shop_domain(shop_domain)
            
            url = f"https://{shop}/admin/oauth/access_token"
            
            logger.info(f"Exchanging code for token for shop: {shop}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json={
                        "client_id": self.api_key,
                        "client_secret": self.api_secret,
                        "code": code,
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                token_data = response.json()
                
                # Log success (but not the token itself)
                logger.info(f"Successfully exchanged code for token for shop: {shop}")
                return token_data
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Token exchange failed for shop {shop_domain}: HTTP {e.response.status_code} - {e.response.text[:200]}")
            raise
        except Exception as e:
            logger.error(f"Token exchange error for shop {shop_domain}: {e}")
            raise
