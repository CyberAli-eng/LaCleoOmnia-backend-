# Frontend API base and routes (Next.js `authFetch()` contract)

## Base URL (important)

In the frontend, `API_BASE_URL` is normalized to **end with `/api`** (see `web/utils/api.ts`).

That means:

- **Frontend must call:** `authFetch("/finance/overview")`, `authFetch("/orders")`, etc.
- **Frontend must NOT call:** `authFetch("/api/finance/overview")` (would become `/api/api/...`)

**Production example API origin (Render):** `https://lacleoomnia-api.onrender.com`  
Frontend env can be either:

- `NEXT_PUBLIC_API_BASE_URL=https://lacleoomnia-api.onrender.com` (recommended), or
- `NEXT_PUBLIC_API_URL=https://lacleoomnia-api.onrender.com/api`

Both work because the frontend normalizes to `{ORIGIN}/api`.

---

## Rule for the frontend

If you are calling the backend **directly** (curl/Postman), you must include `/api`.

- **Correct (direct call):** `https://lacleoomnia-api.onrender.com/api/auth/login`

If you are calling via the frontend helper (`authFetch()`), you must **not** include `/api` in the path.

- **Correct (frontend call):** `authFetch("/auth/login")`

---

## All API routes (direct backend paths: prefix each with `{API_ORIGIN}/api`)

### Auth — prefix `/api/auth`
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/register` | Register (sign up) |
| POST | `/api/auth/signup` | Sign up (alias for register) |
| GET | `/api/auth/me` | Current user (requires Bearer token) |
| POST | `/api/auth/logout` | Logout |
| POST | `/api/auth/forgot-password` | Forgot password |
| POST | `/api/auth/reset-password` | Reset password |

### Channels — prefix `/api/channels`
| Method | Path |
|--------|------|
| GET | `/api/channels` |
| POST | `/api/channels/shopify/connect` |
| POST | `/api/channels/shopify/test` |
| POST | `/api/channels/shopify/import-orders` |
| GET | `/api/channels/shopify/oauth/install` |
| GET | `/api/channels/shopify/oauth/callback` |

### Orders — prefix `/api/orders`
| Method | Path |
|--------|------|
| GET | `/api/orders` |
| GET | `/api/orders/{order_id}` |
| POST | `/api/orders/{order_id}/confirm` |
| POST | `/api/orders/{order_id}/pack` |
| POST | `/api/orders/{order_id}/ship` |
| POST | `/api/orders/{order_id}/cancel` |

### Users — prefix `/api/users`
| Method | Path |
|--------|------|
| GET | `/api/users` |
| POST | `/api/users` |
| PATCH | `/api/users/{user_id}` |
| DELETE | `/api/users/{user_id}` |

### Warehouses — prefix `/api/warehouses`
| Method | Path |
|--------|------|
| GET | `/api/warehouses` |
| POST | `/api/warehouses` |
| PATCH | `/api/warehouses/{warehouse_id}` |

### Products — prefix `/api/products`
| Method | Path |
|--------|------|
| GET | `/api/products` |
| POST | `/api/products` |
| GET | `/api/products/{product_id}` |
| PATCH | `/api/products/{product_id}` |
| DELETE | `/api/products/{product_id}` |

### Inventory — prefix `/api/inventory`
| Method | Path |
|--------|------|
| GET | `/api/inventory` |
| POST | `/api/inventory/adjust` |

### Config — prefix `/api/config`
| Method | Path |
|--------|------|
| GET | `/api/config/status` |
| POST | `/api/config` |
| PATCH | `/api/config/{integration_id}` |
| DELETE | `/api/config/{integration_id}` |
| POST | `/api/config/cleanup` |

### Workers — prefix `/api/workers`
| Method | Path |
|--------|------|
| GET | `/api/workers` |
| POST | `/api/workers/{job_id}/{action}` |

### Webhooks — prefix `/api/webhooks`
| Method | Path |
|--------|------|
| POST | `/api/webhooks/register/{integration_id}` |
| GET | `/api/webhooks` |
| GET | `/api/webhooks/events` |
| POST | `/api/webhooks/shopify` |
| POST | `/api/webhooks/events/{event_id}/retry` |
| GET | `/api/webhooks/subscriptions` |

### Sync — prefix `/api/sync`
| Method | Path |
|--------|------|
| GET | `/api/sync/jobs` |
| POST | `/api/sync/orders/{account_id}` |
| POST | `/api/sync/inventory/{account_id}` |
| POST | `/api/sync/reconcile/{account_id}` |
| GET | `/api/sync/history/{account_id}` |

### SKU costs — prefix `/api/sku-costs`
| Method | Path |
|--------|------|
| GET | `/api/sku-costs` |
| POST | `/api/sku-costs/bulk` |
| GET | `/api/sku-costs/{sku}` |
| POST | `/api/sku-costs` |
| PATCH | `/api/sku-costs/{sku}` |
| DELETE | `/api/sku-costs/{sku}` |

### Shipments — prefix `/api/shipments`
| Method | Path |
|--------|------|
| GET | `/api/shipments` |
| GET | `/api/shipments/order/{order_id}` |
| POST | `/api/shipments` |
| POST | `/api/shipments/generate-label` |
| POST | `/api/shipments/sync` |
| GET | `/api/shipments/{shipment_id}` |

### Logistics analytics — prefix `/api/logistics`
| Method | Path |
|--------|------|
| GET | `/api/logistics/rto` |

### Profit — prefix `/api/profit`
| Method | Path |
|--------|------|
| POST | `/api/profit/recompute` | Optional query: `?order_id=...` |

### Marketplaces — prefix `/api/marketplaces`
| Method | Path |
|--------|------|
| GET | `/api/marketplaces/shopify/shop` |

### Labels — prefix `/api/labels`
| Method | Path |
|--------|------|
| GET | `/api/labels` |
| POST | `/api/labels/generate` |

### Integrations — prefix `/api/integrations`
| Method | Path |
|--------|------|
| GET | `/api/integrations/catalog` |
| GET | `/api/integrations/connected-summary` |
| GET | `/api/integrations/providers/shopify_app/status` |
| POST | `/api/integrations/providers/shopify_app/connect` |
| GET | `/api/integrations/providers/{provider_id}/status` |
| POST | `/api/integrations/providers/{provider_id}/connect` |
| POST | `/api/integrations/providers/amazon/sync` |
| POST | `/api/integrations/providers/flipkart/sync` |
| POST | `/api/integrations/providers/myntra/sync` |
| POST | `/api/integrations/ad-spend/sync` |
| POST | `/api/integrations/shopify/register-webhooks` |
| GET | `/api/integrations/shopify/status` |
| GET | `/api/integrations/shopify/orders` |
| GET | `/api/integrations/shopify/inventory` |
| POST | `/api/integrations/shopify/sync/orders` |
| POST | `/api/integrations/shopify/sync` |

### Finance — prefix `/api/finance` (golden endpoints)
| Method | Path | Used by |
|--------|------|---------|
| GET | `/api/finance/overview` | Dashboard |
| GET | `/api/finance/orders/{order_id}` | Orders drawer |
| GET | `/api/finance/pnl` | P&L page |
| GET | `/api/finance/settlements` | Settlements page |
| GET | `/api/finance/risk` | Risk page |
| GET | `/api/finance/ads` | Ads page |
| POST | `/api/finance/expenses` | Manual expense create |
| PATCH | `/api/finance/expense/{expense_id}` | Manual expense edit |
| DELETE | `/api/finance/expense/{expense_id}` | Manual expense delete |
| GET | `/api/finance/expense-rules` | Settings page |
| POST | `/api/finance/expense-rules` | Settings page |
| PATCH | `/api/finance/expense-rules/{rule_id}` | Settings page |

### Audit — prefix `/api/audit`
| Method | Path |
|--------|------|
| GET | `/api/audit` |

### Analytics — prefix `/api/analytics`
| Method | Path |
|--------|------|
| GET | `/api/analytics/overview` |
| GET | `/api/analytics/summary` |
| GET | `/api/analytics/profit-summary` |

---

## Non-API routes (no /api prefix, on same origin)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/auth/shopify` | Shopify app URL redirect |
| GET | `/auth/shopify/callback` | Shopify OAuth callback (backend only) |

Use these only for health checks or OAuth; all app-to-API calls must go to `/api/...`.
