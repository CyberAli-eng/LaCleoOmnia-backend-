# Environment Configuration Guide

## Quick Start

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Set your environment:**
   ```bash
   # For development
   ENV=DEV
   
   # For production
   ENV=PROD
   ```

3. **The system automatically detects:**
   - ✅ Localhost vs Cloud (Render/Vercel)
   - ✅ Development vs Production mode
   - ✅ CORS origins based on environment
   - ✅ Logging levels
   - ✅ API documentation visibility

## Environment Variables

### Required

- `ENV` - Set to `DEV` or `PROD` (defaults to `DEV`)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET` - Secure random string for JWT tokens

### Optional (with smart defaults)

- `HOST` - Server host (auto: `127.0.0.1` for local, `0.0.0.0` for cloud)
- `PORT` - Server port (default: `8000`)
- `ALLOWED_ORIGINS` - Comma-separated CORS origins (recommended in production to avoid CORS issues)
- `DEFAULT_WAREHOUSE_NAME` - Name of default warehouse for order confirm/pack/ship (default: `Main Warehouse`)
- `DEFAULT_WAREHOUSE_ID` - Optional: warehouse ID to use as default (overrides name if set)
- `WEBHOOK_BASE_URL` - Base URL for webhooks (e.g. `https://yourapi.onrender.com`)
- `ENCRYPTION_KEY` - 32-character encryption key (for ProviderCredential, etc.)
- `LOG_LEVEL` - Logging level (default: `INFO` for prod, `DEBUG` for dev)
- `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`, `SHOPIFY_SCOPES` - Optional; used when user has not set credentials in UI
- `DELHIVERY_API_KEY`, `DELHIVERY_TRACKING_BASE_URL` - Optional; for unified shipment sync (Delhivery)
- `SELLOSHIP_API_KEY`, `SELLOSHIP_API_BASE_URL` - Optional; for unified shipment sync (Selloship). If using token-based auth per Base.com Shipper Integration, also set `SELLOSHIP_USERNAME` and `SELLOSHIP_PASSWORD` (POST /authToken used to obtain Bearer token).
- `SELLOSHIP_USERNAME`, `SELLOSHIP_PASSWORD` - Optional; for Selloship when using Base.com Shipper Integration auth (POST /authToken). When set, token is used in Authorization header for /waybillDetails.
- `SHIPMENT_POLL_INTERVAL_SEC`, `SHIPMENT_POLL_FIRST_DELAY_SEC` - Optional; default 1800 (30 min), 120 (first run delay)
- `MOCK_DATA` - Optional; set to `true`, `1`, or `yes` to enable mock API (fixture data for orders, inventory, analytics, etc.; no DB required). See `API_LIST.md` in repo root.

## Automatic Detection

The system automatically detects:

### Cloud Platforms
- ✅ Render (via `RENDER` env var or auto-detection)
- ✅ Vercel (via `VERCEL` env var or auto-detection)
- ✅ Heroku (via `DYNO` env var)
- ✅ Railway (via `RAILWAY_ENVIRONMENT` env var)

### Environment Behavior

**Development (ENV=DEV):**
- API docs enabled at `/docs`
- Auto-reload enabled
- Debug logging
- Localhost CORS origins
- Relaxed security

**Production (ENV=PROD):**
- API docs disabled
- No auto-reload
- Info-level logging
- Vercel pattern CORS
- Production security

## Example .env Files

### Development (.env)
```env
ENV=DEV
DATABASE_URL=postgresql://admin:password@localhost:5432/lacleo_omnia
JWT_SECRET=dev-secret-key-change-in-production
ENCRYPTION_KEY=dev-encryption-key-32-chars!!
LOG_LEVEL=DEBUG
```

### Production (.env)
```env
ENV=PROD
DATABASE_URL=postgresql://user:pass@host:5432/dbname
JWT_SECRET=super-secure-random-secret-here
ENCRYPTION_KEY=production-encryption-key-32!!
ALLOWED_ORIGINS=https://your-app.vercel.app
WEBHOOK_BASE_URL=https://your-backend.onrender.com
LOG_LEVEL=INFO
```

## Render Deployment

Set these in Render dashboard:

```env
ENV=PROD
DATABASE_URL=your_postgresql_url
JWT_SECRET=your_secure_secret
ENCRYPTION_KEY=your-32-character-key
WEBHOOK_BASE_URL=https://your-service.onrender.com
```

The system will automatically:
- ✅ Detect it's running on Render
- ✅ Use `0.0.0.0` as host
- ✅ Allow all Vercel deployments via CORS
- ✅ Disable API docs
- ✅ Use production logging

## Vercel Frontend

Set in Vercel dashboard:

```env
NEXT_PUBLIC_API_URL=https://your-backend.onrender.com/api
```

The backend will automatically allow your Vercel deployment via CORS regex pattern.

## Testing

Check environment detection:

```bash
# Start the server
python -m uvicorn main:app --reload

# Check logs - you'll see:
# 🚀 Starting LaCleoOmnia API
# 📊 Environment: DEV
# 🌐 Production: False
# ☁️  Cloud: False
# 🔗 Host: 127.0.0.1:8000
```

## Best Practices

1. **Never commit `.env` files** - Use `.env.example` as template
2. **Use strong secrets in production** - Generate random strings
3. **Set ENV=PROD in production** - Enables security features
4. **Use environment-specific databases** - Separate dev/prod
5. **Monitor logs** - Check LOG_LEVEL for appropriate verbosity
