# Postman collection – LaCleoOmnia API

All APIs are stored in a **structural manner** (like the reference in your screenshot): folders by domain (Auth, Orders, Inventory, Integrations, etc.) and each request named **METHOD + Action** (e.g. **GET List orders**, **POST Login**, **PATCH Update SKU cost**). Key requests include an **e.g. Success Response** example.

---

## Base URL: Local vs Production (localhost)

| Environment | When to use | `base_url` |
|-------------|-------------|------------|
| **LaCleoOmnia – Local** | Development on your machine | `http://localhost:8000` |
| **LaCleoOmnia – Production** | Deployed backend (e.g. Render) | `https://lacleoomnia-api.onrender.com` |

**In Postman:** Use the **environment** dropdown (top right). Choose **LaCleoOmnia – Local** when calling **localhost**; choose **LaCleoOmnia – Production** when calling the live API. Every request uses `{{base_url}}`, so switching the environment switches the host without editing requests.

---

## Import

1. Open **Postman**.
2. **Import** → drag and drop (or choose):
   - `LaCleoOmnia-API.postman_collection.json`
   - `LaCleoOmnia-Local.postman_environment.json` and/or `LaCleoOmnia-Production.postman_environment.json`.
3. In the top-right dropdown, select **LaCleoOmnia – Local** (for localhost) or **LaCleoOmnia – Production**.

## Variables

| Variable   | Description |
|-----------|-------------|
| `base_url` | API base URL (no trailing slash). Set by environment: Local = `http://localhost:8000`, Production = `https://lacleoomnia-api.onrender.com`. |
| `token`   | JWT from **Auth → POST Login**. Auto-saved by the collection script. |
| `order_id`| Use in Orders / Shipments requests; set from a list-orders response. |
| `settlement_id` | Use in Finance → Update Settlement. |
| `expense_id` | Use in Finance → Update/Delete Manual Expense. |
| `rule_id` | Use in Finance → Update Expense Rule. |
| `customer_id` | Use in Finance → Customer Risk. |
| `account_id` | Use in Sync endpoints (`/api/sync/orders/{account_id}` etc.). |
| `user_id` | Use in Users PATCH/DELETE. |
| `event_id`| Use in Webhooks → Retry event. |

## Quick start

1. Set **environment** to **LaCleoOmnia – Local** (or Production).
2. Run **Auth → Login** (body: `admin@local` / `Admin@123` for local seed).
3. Copy the `token` from the response into the environment variable **token**.
4. Other requests in the collection use **Bearer {{token}}** automatically.

## Auto-save token after login

The **Login** request has a test script that saves the returned `token` into the collection variable `token`. After you run **Auth → Login**, all other requests (which use Bearer `{{token}}`) will use that token automatically. If you use an environment, you can also copy the token into the environment variable `token` for consistency.

## Collection structure (all APIs in one place)

| Folder | Requests (METHOD + Action) |
|--------|----------------------------|
| **Health** | GET Health check |
| **Auth** | POST Login, POST Register, GET Get current user (me), POST Logout |
| **Orders** | GET List orders, GET Get order by ID, POST Confirm order, POST Pack order, POST Ship order, POST Cancel order |
| **Inventory** | GET List inventory, POST Adjust inventory |
| **Integrations** | GET Get catalog, GET Get provider status, POST Connect provider, GET Get Shopify app status, POST Connect Shopify app, GET Get Shopify status, GET Get Shopify orders, GET Get Shopify inventory, POST Sync Shopify, POST Register Shopify webhooks, POST Sync ad spend |
| **Shipments** | GET List shipments, GET Get shipment by order ID, POST Create shipment, POST Sync shipments |
| **Analytics** | GET Get summary, GET Get profit summary |
| **SKU Costs** | GET List SKU costs, GET Get SKU cost by SKU, POST Create SKU cost, PATCH Update SKU cost, DELETE Delete SKU cost |
| **Profit** | POST Recompute profit |
| **Config** | GET Get config status |
| **Webhooks** | GET List webhooks, GET List subscriptions, GET List events, POST Retry webhook event |
| **Workers** | GET List workers |
| **Sync** | GET List sync jobs |
| **Users** | GET List users, POST Create user, PATCH Update user, DELETE Delete user |
| **Audit** | GET List audit log |
| **Labels** | GET List labels, POST Generate label |

**Success examples:** **Auth → POST Login** and **Orders → GET List orders** include an **e.g. Success Response** so you can see the response shape without calling the API.

For full API details, mock data, and example payloads, see repo root **API_LIST.md**.

---

# LaCleoOmnia Channels API Collection

## Overview

The **LaCleoOmnia-Channels.postman_collection.json** is a comprehensive API collection specifically designed for testing and managing all channel integrations. It provides organized folders for each channel (Commerce, Marketing, and Logistics) with all relevant endpoints for connection, data fetching, and synchronization.

## Channel Categories

### 🛍️ Commerce & Marketplaces
- **Shopify** - Complete e-commerce platform integration
- **Amazon** - SP-API marketplace integration  
- **Flipkart** - Indian marketplace API integration
- **Myntra** - Fashion marketplace API integration

### 📱 Marketing Channels
- **Meta Ads** - Facebook/Instagram advertising platform
- **Google Ads** - Google advertising platform

### 🚚 Logistics & Supply Chain
- **Delhivery** - Indian logistics and courier service
- **Selloship** - Shipping and fulfillment platform

## Quick Start Guide

### 1. Import the Collection
```bash
1. Open Postman
2. Click Import → Select Files
3. Choose "LaCleoOmnia-Channels.postman_collection.json"
4. Select environment (Local or Production)
```

### 2. Authentication Setup
1. **Health & Auth → POST Login**
   - Local: `admin@local` / `Admin@123`
   - Production: Use your actual credentials
2. Token is automatically saved to `{{token}}` variable

### 3. Channel Connection Workflow

#### Shopify (OAuth Flow)
1. **Integration Management → GET Shopify App Status** - Check if app credentials are configured
2. **Integration Management → POST Configure Shopify App** - Add your Shopify App API Key & Secret
3. **Shopify → GET OAuth Install URL** - Generate OAuth install URL
4. **Shopify → POST Test Shopify Connection** - Test connection before saving
5. **Shopify → POST Import Shopify Orders** - Import orders from your store

#### Amazon (SP-API)
1. **Amazon → GET Amazon Status** - Check connection status
2. **Amazon → POST Connect Amazon** - Add SP-API credentials:
   ```json
   {
     "seller_id": "your-seller-id",
     "refresh_token": "your-lwa-refresh-token", 
     "client_id": "your-lwa-client-id",
     "client_secret": "your-lwa-client-secret",
     "marketplace_id": "A21TJRUUN4KGV"
   }
   ```
3. **Amazon → POST Sync Amazon Orders** - Start order synchronization

#### Flipkart
1. **Flipkart → GET Flipkart Status** - Check connection status
2. **Flipkart → POST Connect Flipkart** - Add API credentials:
   ```json
   {
     "seller_id": "your-flipkart-seller-id",
     "client_id": "your-flipkart-client-id", 
     "client_secret": "your-flipkart-client-secret"
   }
   ```
3. **Flipkart → POST Sync Flipkart Orders** - Start order synchronization

#### Myntra
1. **Myntra → GET Myntra Status** - Check connection status
2. **Myntra → POST Connect Myntra** - Add API credentials:
   ```json
   {
     "seller_id": "your-myntra-partner-id",
     "apiKey": "your-myntra-api-key"
   }
   ```
3. **Myntra → POST Sync Myntra Orders** - Start order synchronization

#### Meta Ads
1. **Meta Ads → GET Meta Ads Status** - Check connection status
2. **Meta Ads → POST Connect Meta Ads** - Add credentials:
   ```json
   {
     "ad_account_id": "123456789",
     "access_token": "your-meta-ads-access-token"
   }
   ```

#### Google Ads
1. **Google Ads → GET Google Ads Status** - Check connection status
2. **Google Ads → POST Connect Google Ads** - Add OAuth2 credentials:
   ```json
   {
     "developer_token": "your-google-ads-developer-token",
     "client_id": "your-oauth2-client-id",
     "client_secret": "your-oauth2-client-secret", 
     "refresh_token": "your-oauth2-refresh-token",
     "customer_id": "1234567890"
   }
   ```

#### Delhivery
1. **Delhivery → GET Delhivery Status** - Check connection status
2. **Delhivery → POST Connect Delhivery** - Add API key:
   ```json
   {
     "apiKey": "your-delhivery-api-key"
   }
   ```
3. **Delhivery → POST Sync Delhivery Shipments** - Sync shipment tracking

#### Selloship
1. **Selloship → GET Selloship Status** - Check connection status
2. **Selloship → POST Connect Selloship** - Add credentials:
   ```json
   {
     "username": "your-selloship-username",
     "password": "your-selloship-password"
   }
   ```
3. **Selloship → POST Sync Selloship Shipments** - Sync shipment tracking

## API Call Examples

### Check All Connected Integrations
```http
GET {{base_url}}/api/integrations/connected-summary
Authorization: Bearer {{token}}
```

### Get Integration Catalog
```http
GET {{base_url}}/api/integrations/catalog
Authorization: Bearer {{token}}
```

### Sync All Marketing Ad Spend
```http
POST {{base_url}}/api/integrations/ad-spend/sync
Authorization: Bearer {{token}}
```

### Monitor Sync Jobs
```http
GET {{base_url}}/api/sync/jobs
Authorization: Bearer {{token}}
```

## Common Workflows

### 1. Daily Data Sync Routine
1. **Health & Auth → POST Login** - Authenticate
2. **Integration Management → GET Connected Summary** - Verify all connections
3. **Commerce Channels** - Run sync for each connected marketplace
4. **Marketing Channels** - Sync ad spend data
5. **Logistics Channels** - Sync shipment tracking
6. **Data Sync & Jobs → GET List Sync Jobs** - Monitor sync status

### 2. New Channel Setup
1. **Integration Management → GET Integration Catalog** - View available channels
2. Navigate to specific channel folder
3. **GET [Channel] Status** - Check current status
4. **POST Connect [Channel]** - Add credentials
5. **POST Sync [Channel]** - Test data fetch
6. **Data Sync & Jobs → GET List Workers** - Verify background processing

### 3. Troubleshooting
1. **Health & Auth → GET Health check** - Verify API status
2. **Integration Management → GET Connected Summary** - Check connection status
3. **Data Sync & Jobs → GET List Sync Jobs** - Check for failed jobs
4. **Data Sync & Jobs → GET List Workers** - Check worker status
5. Individual channel status endpoints for detailed diagnostics

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `base_url` | API base URL | `http://localhost:8000` |
| `token` | JWT authentication token | Auto-saved after login |
| `shopify_account_id` | Shopify account ID for imports | `acc_123456789` |

## Response Formats

### Success Response Example
```json
{
  "connected": true,
  "message": "Credentials saved",
  "accountId": "acc_123456789"
}
```

### Error Response Example
```json
{
  "detail": "Missing required fields: seller_id, refresh_token"
}
```

## Best Practices

1. **Always authenticate first** - Run login before other requests
2. **Test connections before syncing** - Use status endpoints to verify connectivity
3. **Monitor sync jobs** - Check sync job status after large imports
4. **Use environment variables** - Keep credentials in environment, not in requests
5. **Handle rate limits** - Some APIs have rate limits, use sync endpoints judiciously

## Troubleshooting Common Issues

### Authentication Errors
- Ensure you've run **POST Login** successfully
- Check that `{{token}}` variable is populated
- Verify token hasn't expired

### Connection Failures
- Check API credentials in connection requests
- Verify network connectivity to external services
- Use **GET [Channel] Status** to diagnose issues

### Sync Job Failures
- Check **GET List Sync Jobs** for error messages
- Verify channel credentials are still valid
- Ensure background workers are running: **GET List Workers**

### Rate Limiting
- Some marketplaces (Amazon, Flipkart) have strict rate limits
- Use sync endpoints during off-peak hours
- Monitor sync job frequency to avoid API throttling

## Support

For API-specific issues:
1. Check individual channel documentation
2. Use status endpoints for diagnostics
3. Monitor sync jobs for error details
4. Refer to main API documentation in repo root
