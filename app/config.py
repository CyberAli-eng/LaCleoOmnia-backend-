"""
Application configuration with automatic environment detection
"""
import os
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Application settings with automatic environment detection"""
    
    # Environment detection
    ENV = os.getenv("ENV", "DEV").upper()
    IS_PRODUCTION = ENV == "PROD" or ENV == "PRODUCTION"
    IS_DEVELOPMENT = not IS_PRODUCTION
    
    # Auto-detect if running on Render/Vercel/Heroku/Railway
    # Render sets RENDER=true, Vercel sets VERCEL=true, Heroku sets DYNO, Railway sets RAILWAY_ENVIRONMENT
    RENDER = os.getenv("RENDER", "").lower() == "true" or "render.com" in os.getenv("RENDER_EXTERNAL_URL", "")
    VERCEL = os.getenv("VERCEL", "").lower() == "true"
    HEROKU = bool(os.getenv("DYNO"))
    RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))
    IS_CLOUD = RENDER or VERCEL or HEROKU or RAILWAY
    
    # Server configuration
    HOST = os.getenv("HOST", "0.0.0.0" if IS_CLOUD else "127.0.0.1")
    PORT = int(os.getenv("PORT", 8000))
    
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/lacleo_omnia?schema=public")
    
    # Authentication
    JWT_SECRET = os.getenv("JWT_SECRET", "supersecret_fallback_key_change_in_production")
    AUTH_ALGORITHM = os.getenv("AUTH_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))  # 7 days
    
    # Encryption
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "your-32-character-encryption-key!!")
    
    # CORS - Fully dynamic based on ALLOWED_ORIGINS environment variable
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Get allowed CORS origins - fully dynamic from environment variable"""
        origins = []
        
        # Always add localhost origins in development (for local testing)
        if self.IS_DEVELOPMENT:
            origins.extend([
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
            ])
        
        # Add origins from ALLOWED_ORIGINS environment variable (comma-separated)
        # This works for ANY platform - Vercel, Netlify, Cloudflare Pages, custom domains, etc.
        env_origins = os.getenv("ALLOWED_ORIGINS", "")
        if env_origins:
            # Split by comma and clean up each origin
            for origin in env_origins.split(","):
                origin = origin.strip()
                if origin:
                    origins.append(origin)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_origins = []
        for origin in origins:
            if origin not in seen:
                seen.add(origin)
                unique_origins.append(origin)
        
        return unique_origins
    
    @property
    def CORS_ORIGIN_REGEX(self) -> Optional[str]:
        """Get CORS origin regex pattern - optional, only if CORS_ORIGIN_REGEX env var is set"""
        # Only use regex if explicitly provided via environment variable
        # This allows flexibility for platforms that need regex patterns (e.g., preview deployments)
        regex = os.getenv("CORS_ORIGIN_REGEX", "")
        if regex:
            return regex
        
        # Default: no regex pattern (use ALLOWED_ORIGINS only)
        # In development, allow any localhost port for flexibility
        if self.IS_DEVELOPMENT:
            return r"http://localhost:\d+|http://127\.0\.0\.1:\d+"
        
        # In production, no regex by default - use ALLOWED_ORIGINS only
        return None
    
    # Default warehouse for order confirm/pack/ship/cancel (name or id)
    DEFAULT_WAREHOUSE_NAME = os.getenv("DEFAULT_WAREHOUSE_NAME", "Main Warehouse")
    DEFAULT_WAREHOUSE_ID = os.getenv("DEFAULT_WAREHOUSE_ID", "")  # optional: prefer by id if set

    # Webhooks
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")
    
    # Shopify OAuth
    SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "")
    SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET", "")
    # read_locations is REQUIRED for inventory_levels API; without it inventory sync returns 403/empty
    SHOPIFY_SCOPES = os.getenv(
        "SHOPIFY_SCOPES",
        "read_orders,write_orders,read_products,write_products,read_inventory,write_inventory,read_locations",
    )
    
    # Delhivery tracking
    DELHIVERY_API_KEY = os.getenv("DELHIVERY_API_KEY", "")
    DELHIVERY_TRACKING_BASE_URL = os.getenv("DELHIVERY_TRACKING_BASE_URL", "https://track.delhivery.com")

    # Selloship (auth: selloship.com; API may be api.selloship.com)
    SELLOSHIP_API_KEY = os.getenv("SELLOSHIP_API_KEY", "")
    SELLOSHIP_API_BASE_URL = os.getenv("SELLOSHIP_API_BASE_URL", "https://api.selloship.com")
    SELLOSHIP_AUTH_URL = os.getenv("SELLOSHIP_AUTH_URL", "https://selloship.com/api/lock_actvs/channels/authToken")
    SELLOSHIP_USERNAME = os.getenv("SELLOSHIP_USERNAME", "")
    SELLOSHIP_PASSWORD = os.getenv("SELLOSHIP_PASSWORD", "")
    
    # Mock API (return fixture data for key endpoints; no DB required)
    MOCK_DATA = os.getenv("MOCK_DATA", "").lower() in ("1", "true", "yes")

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if IS_PRODUCTION else "DEBUG")
    
    # API Configuration
    API_PREFIX = "/api"
    API_V1_PREFIX = "/api/v1"
    
    # Security
    ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",") if os.getenv("ALLOWED_HOSTS") else ["*"]

    # Password reset email (optional)
    FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/") or "http://localhost:3000"
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@lacleoomnia.com")
    
    def __str__(self):
        return f"Settings(ENV={self.ENV}, IS_PRODUCTION={self.IS_PRODUCTION}, IS_CLOUD={self.IS_CLOUD})"

# Global settings instance
settings = Settings()
