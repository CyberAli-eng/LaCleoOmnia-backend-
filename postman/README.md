# Postman collection – LaCleoOmnia API

All APIs are stored in a **structural manner** (like the reference in your screenshot): folders by domain (Auth, Orders, Inventory, Integrations, etc.) and each request named **METHOD + Action** (e.g. **GET List orders**, **POST Login**, **PATCH Update SKU cost**). Key requests include an **e.g. Success Response** example.

---

## Base URL: Local vs Production (localhost)

| Environment | When to use | `base_url` |
|-------------|-------------|------------|
| **LaCleoOmnia – Local** | Development on your machine | `http://localhost:8000` |
| **LaCleoOmnia – Production** | Deployed backend (e.g. Render) | `https://lacleoomnia-api.onrender.com/` |

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
| `base_url` | API base URL (no trailing slash). Set by environment: Local = `http://localhost:8000`, Production = `https://lacleoomnia.onrender.com`. |
| `token`   | JWT from **Auth → POST Login**. Auto-saved by the collection script. |
| `order_id`| Use in Orders / Shipments requests; set from a list-orders response. |
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
