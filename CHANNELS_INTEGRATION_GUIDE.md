### Overview

This project connects multiple **commerce**, **marketing**, and **logistics** channels through a common data model (`Order`, `Shipment`, `ChannelAccount`, `ProviderCredential`) and a shared sync engine.

- **Commerce**: Shopify, Amazon, Flipkart, Myntra
- **Marketing**: Meta Ads, Google Ads
- **Logistics**: Delhivery, Selloship

Frontend should **not hardcode** providers or URLs. It should always drive UI from the dynamic integration catalog exposed by `GET /api/integrations/catalog`.

---

### 1. Core Concepts

- **Channel**: High‑level enum (`ChannelType`) such as `SHOPIFY`, `AMAZON`, `FLIPKART`, `MYNTRA`.
- **ChannelAccount**: A user’s connection to a channel (e.g. one Shopify store). Used for order sync.
- **ProviderCredential**: Encrypted credentials for non‑order providers (couriers, ad platforms, or marketplace API keys).
- **SyncEngine**: Background/order sync abstraction that imports orders for a given `ChannelAccount`.
- **Background tasks** (in `main.py`):
  - Shipment tracking sync (Delhivery, Selloship)
  - Daily ad spend sync (Meta, Google)

---

### 2. How Each Channel Connects

#### 2.1 Shopify (Commerce)

**Steps to connect:**
1. **Configure app credentials**
   - Endpoint: **`POST /api/integrations/providers/shopify_app/connect`**
   - Stores API Key + Secret in `ProviderCredential` (`provider_id="shopify_app"`).
2. **OAuth install flow (frontend)**:
   - Use catalog entry with:
     - `oauthInstallEndpoint: "/channels/shopify/oauth/install"`
     - `oauthInstallQueryKey: "shop"`
   - Backend auth callback saves:
     - `ChannelAccount` (per user + shop)
     - Encrypted **access token** on the account
     - Optional `ShopifyIntegration` row for app‑level info.
3. **Webhooks (optional but recommended)**:
   - Per‑user route: **`POST /api/integrations/shopify/register-webhooks`**
   - Or by `ChannelAccount` id: **`POST /api/webhooks/register/{integration_id}`**

**Using Shopify after connect:**
- **Check connection**: `GET /api/integrations/shopify/status`
- **Manual sync (simple)**:
  - Orders only: `POST /api/integrations/shopify/sync/orders`
  - Orders + inventory: `POST /api/integrations/shopify/sync`
- **Inventory (cached)**:
  - `GET /api/integrations/shopify/inventory?refresh=false` (DB cache)
  - `GET /api/integrations/shopify/inventory?refresh=true` (hits Shopify + updates cache)

Webhook receiver:
- Public endpoint (no JWT): **`POST /api/webhooks/shopify`**
- Verifies `X-Shopify-Hmac-Sha256` using candidate secrets from:
  - `ShopifyIntegration.app_secret_encrypted`
  - Per‑user `ProviderCredential("shopify_app")`
  - `SHOPIFY_API_SECRET` env
- Persists `WebhookEvent`, then calls `process_shopify_webhook`, which updates orders, inventory, and profit.

#### 2.2 Amazon, Flipkart, Myntra (Commerce)

All three share a **unified pattern**:

1. **Save credentials**:
   - Generic endpoint: `POST /api/integrations/providers/{provider_id}/connect`
   - `provider_id` in: `amazon`, `flipkart`, `myntra`
   - Required fields per provider are validated by `PROVIDER_REQUIRED_KEYS` in `integrations.py`.
   - Credentials stored encrypted in `ProviderCredential` per user.
   - For commerce providers, a `ChannelAccount` is also created/ensured for the current user.

2. **Trigger sync** (backend runs in background):
   - **Amazon**: `POST /api/integrations/providers/amazon/sync`
   - **Flipkart**: `POST /api/integrations/providers/flipkart/sync`
   - **Myntra**: `POST /api/integrations/providers/myntra/sync`
   - All of these:
     - Resolve the current user’s `ChannelAccount`
     - Call `SyncEngine(db).sync_orders(account)`

3. **Import logic**:
   - Implemented in `app/services/order_import.py`:
     - `import_amazon_orders`
     - `import_flipkart_orders`
     - `import_myntra_orders`
   - All normalize channel‑specific payloads into a **common order format**, then call `_persist_one_common_order` which:
     - Creates `Order` + `OrderItem` records
     - Reserves inventory in the default warehouse
     - Logs `SyncJob` + `SyncLog`

#### 2.3 Meta Ads, Google Ads (Marketing)

1. **Save credentials** via generic provider connect:
   - Meta Ads: `POST /api/integrations/providers/meta_ads/connect`
   - Google Ads: `POST /api/integrations/providers/google_ads/connect`

2. **Automatic daily sync**:
   - Background task in `main.py` runs `sync_ad_spend_for_date` for each connected provider at **00:30 IST**.
   - Syncs into `ad_spend_daily` equivalents and triggers **profit recalculation** for affected orders.

3. **Manual sync**:
   - `POST /api/integrations/ad-spend/sync`
     - Uses yesterday (IST)
     - Calls `sync_ad_spend_for_date`
     - Recomputes profit for orders created that day.

#### 2.4 Delhivery, Selloship (Logistics)

1. **Save credentials**:
   - Delhivery: `POST /api/integrations/providers/delhivery/connect` (API key)
   - Selloship: `POST /api/integrations/providers/selloship/connect` (username/password, validated by calling Selloship API).

2. **Shipment sync**:
   - Background loop in `main.py` periodically calls the shipment sync service:
     - Uses saved credentials (or env overrides) to:
       - Fetch latest tracking state
       - Update `Shipment` records
       - Potentially trigger profit recalculation.

3. **Labels** (Selloship):
   - Exposed via `/api/shipments/generate-label` (see shipments controller).

---

### 3. How Channels Are Discovered by the Frontend

Use these endpoints, **do not hardcode lists of providers in the frontend**:

- **Integration catalog**:
  - `GET /api/integrations/catalog`
  - Returns `sections` → `providers` with:
    - `id`, `name`, `icon`, `color`
    - `connectType` (`oauth` | `api_key`)
    - Endpoints: `statusEndpoint`, `connectEndpoint` / `oauthInstallEndpoint`
    - Optional `setupFormFields`, `setupSteps`, `actions`

- **Connected summary (sidebar/badges)**:
  - `GET /api/integrations/connected-summary`
  - Combines:
    - `ChannelAccount` (SHOPIFY/AMAZON/FLIPKART/MYNTRA)
    - `ProviderCredential` (meta_ads, google_ads, delhivery, selloship)

- **Webhook subscriptions**:
  - `GET /api/webhooks/subscriptions`
  - Returns current user’s `ChannelAccount`s as generic subscription rows (for a “webhooks” screen).

---

### 4. Adding a New Channel (Checklist)

Use this pattern for **any new provider** so everything stays consistent.

1. **Decide provider type**
   - Commerce (orders): use `Channel` + `ChannelAccount` + `SyncEngine.sync_orders`
   - Logistics (shipments): use `ProviderCredential` + shipment sync service
   - Marketing (ad spend): use `ProviderCredential` + ad spend sync service

2. **Models & constants**
   - If commerce:
     - Add enum value in `ChannelType` (models).
     - Ensure channel row exists or is created lazily (similar to `_ensure_channel_account_for_marketplace`).
   - Add provider id (string) to:
     - `ALLOWED_CREDENTIAL_PROVIDERS` in `integrations.py`
     - `PROVIDER_REQUIRED_KEYS` with the minimal credential keys.

3. **Service client**
   - Create `<provider>_service.py` with:
     - Auth helpers (tokens / API keys)
     - `get_orders` / `get_shipments` / `get_spend` APIs
     - Optional normalization helpers (to a “common” dict shape).

4. **Import or sync logic**
   - For commerce providers:
     - Add an `import_<provider>_orders` function in `order_import.py`:
       - Resolve credentials using `get_provider_credentials(db, user_id, "<provider>")`.
       - Normalize to a common order structure.
       - Call `_persist_one_common_order`.
     - Wire into `SyncEngine.sync_orders`:
       - Map `channel_name` to your new import function.
   - For logistics / marketing:
     - Add a sync function analogous to `shipment_sync.py` or `ad_spend_sync.py`.
     - Register it in `main.py` background tasks if it should run periodically.

5. **Controllers**
   - **Integrations catalog**:
     - Add a provider entry to the appropriate `section` in `_get_integration_catalog()` with:
       - `id` (string key)
       - Status + connect endpoints
       - Any `connectFormFields` and `setupSteps`.
   - **Connect & status**:
     - Reuse generic:
       - `GET /api/integrations/providers/{provider_id}/status`
       - `POST /api/integrations/providers/{provider_id}/connect`
   - **Manual sync endpoint** (if needed by UI):
     - If commerce: add `POST /api/integrations/providers/<provider>/sync` that:
       - Resolves the current user’s `ChannelAccount`.
       - Calls `SyncEngine(db).sync_orders(account)` in a background task.

6. **Webhooks (optional)**
   - Add a new webhook receiver in `app/http/controllers/webhooks.py` or a new controller module.
   - Verify signatures using provider’s secret from `ProviderCredential` or env.
   - Map payloads to orders/shipments and reuse existing persistence helpers.

---

### 5. Typical Flows (End‑to‑End)

#### 5.1 Connect a commerce channel (e.g. Flipkart) and sync orders

1. Frontend loads catalog from `GET /api/integrations/catalog`.
2. User opens Flipkart card and submits the connect form → `POST /api/integrations/providers/flipkart/connect`.
3. Backend:
   - Validates fields using `PROVIDER_REQUIRED_KEYS`.
   - Saves encrypted credentials in `ProviderCredential`.
   - Ensures a `ChannelAccount` exists for the user + `ChannelType.FLIPKART`.
4. User clicks “Sync orders” action on the card:
   - Triggers `POST /api/integrations/providers/flipkart/sync`.
   - Endpoint:
     - Looks up user’s `ChannelAccount`.
     - Starts background job via `SyncEngine.sync_orders(account)`.
5. UI can poll sync history via `SyncEngine.get_sync_history(account_id)` exposed by a controller (if needed).

#### 5.2 Connect a logistics provider (Delhivery) and track shipments

1. User enters API key in the Delhivery card → `POST /api/integrations/providers/delhivery/connect`.
2. Key is encrypted into `ProviderCredential`.
3. Background shipment sync in `main.py`:
   - Reads credentials from `ProviderCredential` (or env override).
   - Periodically pulls tracking data.
   - Updates `Shipment` and related order profit fields.
4. UI reads shipments and their statuses via `shipments` APIs.

#### 5.3 Connect marketing providers and calculate CAC

1. User connects Meta Ads and/or Google Ads via provider connect endpoints.
2. Daily job (00:30 IST) calls `sync_ad_spend_for_date` for each provider.
3. Spends are attached to the correct date + user.
4. Profit calculator (`compute_profit_for_order`) includes marketing cost when recomputing profit.

---

### 6. Known Design Considerations / Current Limitations

- Shopify has both:
  - Dedicated manual sync endpoints (`/shopify/sync`, `/shopify/sync/orders`), and
  - A more generic `SyncEngine`‑based path via `import_shopify_orders`.
  - **Recommendation**: prefer the `SyncEngine` path for new features and future UI.
- Credential lookup logic exists in multiple places (integrations, webhooks, shipment/ad‑spend sync).
  - **Recommendation**: when adding new channels, use `get_provider_credentials` and keep new logic in service modules rather than duplicating decryption in controllers.
- Multi‑tenant isolation is enforced by `current_user` filters in most queries; any new endpoint must always filter by `user_id` on `ChannelAccount` / `ProviderCredential` / `Order`.

Use this file as the **single source of truth** when adding or modifying integrations. Keep it updated whenever a new provider is introduced or an integration flow changes.

