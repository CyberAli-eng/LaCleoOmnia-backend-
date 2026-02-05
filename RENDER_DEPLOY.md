# Deploy LaCleoOmnia API on Render (Free Tier)

Step-by-step guide to deploy this FastAPI backend on [Render](https://render.com) free tier.

---

## What This Project Is

- **Stack:** FastAPI + PostgreSQL + SQLAlchemy + Alembic
- **Features:** JWT auth, Shopify/Delhivery/Selloship integrations, orders, inventory, profit, webhooks, background sync
- **Entry:** `main.py` (FastAPI app), served with **uvicorn**
- **Database:** PostgreSQL (migrations via Alembic)

---

## 1. Create a Render Account

1. Go to [render.com](https://render.com) and sign up (GitHub login is easiest).
2. Connect your GitHub account so Render can deploy from your repo.

---

## 2. Create a PostgreSQL Database (Free)

1. In Render Dashboard: **New +** → **PostgreSQL**.
2. Name it (e.g. `lacleoomnia-db`).
3. Choose **Free** plan (no credit card for free tier).
4. Region: pick one close to you.
5. Click **Create Database**.
6. Wait until it’s **Available**, then open it.
7. Under **Connections**, copy **Internal Database URL** (use this for the Web Service env).
   - Format: `postgres://user:password@host/dbname` or `postgresql://...`
   - The app normalizes `postgres://` → `postgresql://` automatically.

---

## 3. Create a Web Service (API)

1. **New +** → **Web Service**.
2. Connect the repo that contains this API (e.g. `api-python` or the monorepo).
3. Configure:
   - **Name:** e.g. `lacleoomnia-api`
   - **Region:** same as the DB when possible.
   - **Branch:** `main` (or your default).
   - **Runtime:** **Python 3**.
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     alembic upgrade head && python -m uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
     This runs migrations on every deploy then starts the app. On free tier there is no separate “Release Command”, so this is the recommended approach.
4. **Instance type:** **Free**.

---

## 4. Attach Database and Set Environment Variables

1. In the Web Service → **Environment** tab:
   - Click **Add Environment Variable**.
   - If you didn’t link the DB in step 2: paste **Internal Database URL** from the PostgreSQL service as `DATABASE_URL`.
   - Or use **Link Existing Resource** and select your Postgres DB; Render will add `DATABASE_URL` for you.
2. Add these variables (required for production):

   | Key | Value | Notes |
   |-----|--------|--------|
   | `ENV` | `PROD` | Required for production behavior |
   | `DATABASE_URL` | *(from linked DB or paste Internal URL)* | Postgres connection string |
   | `JWT_SECRET` | *(long random string)* | e.g. `openssl rand -hex 32` |
   | `ENCRYPTION_KEY` | *(32 characters)* | For encrypting tokens (e.g. credentials) |
   | `WEBHOOK_BASE_URL` | `https://YOUR-SERVICE-NAME.onrender.com` | Your Render API URL (no trailing slash) |
   | `ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` | Comma-separated frontend origins |

3. Optional but useful:
   - `LOG_LEVEL` = `INFO`
   - `SHOPIFY_API_KEY` / `SHOPIFY_API_SECRET` if you use a single Shopify app (otherwise set per user in Integrations).

4. **Save Changes**. Render will redeploy.

---

## 5. Deploy and Check

1. First deploy may take a few minutes (install deps, run migrations, start app).
2. When **Live**, open:
   - `https://YOUR-SERVICE-NAME.onrender.com/health`
   - You should see something like: `{"status":"ok","service":"api","db":"ok",...}`.
3. Root: `https://YOUR-SERVICE-NAME.onrender.com/` should return a short JSON message.

---

## 6. Free Tier Limits (Important)

- **Spins down:** After ~15 minutes of no requests, the free instance sleeps. First request after that can take 30–60 seconds (cold start).
- **No Release Command:** Free tier doesn’t support a separate “Release Command”, so migrations are run in the **Start Command** (as above). That’s safe and idempotent.
- **PostgreSQL free:** DB is removed after 90 days unless you upgrade; data is not guaranteed long-term on free.
- **Outbound TLS:** Render uses TLS for outbound connections; your `DATABASE_URL` and APIs work as usual.

---

## 7. After First Deploy (Optional)

- **Seed data:** If you use `seed.py`, run it once against the production DB (e.g. from your machine with `DATABASE_URL` set to the Render **External** URL, or via Render Shell when available). Don’t commit production credentials.
- **Shopify:** In your Shopify app settings, set:
  - App URL: `https://YOUR-SERVICE-NAME.onrender.com/auth/shopify`
  - Redirect URL: `https://YOUR-SERVICE-NAME.onrender.com/auth/shopify/callback`
- **Frontend:** Point your frontend’s API base URL to `https://YOUR-SERVICE-NAME.onrender.com` and set `ALLOWED_ORIGINS` to your frontend origin(s).

---

## 8. Troubleshooting

| Issue | What to do |
|-------|------------|
| **Build fails** | Check **Build logs**; ensure `requirements.txt` and `runtime.txt` (e.g. `python-3.11.9`) are in the repo and that Render is using the correct root directory if the API is in a subdirectory. |
| **DB connection error** | Confirm `DATABASE_URL` is set (from linked DB or manual). Use **Internal Database URL** for services in the same Render account. |
| **502 / Unhealthy** | Check **Logs**. Often the app didn’t start (e.g. missing env, or wrong **Start Command**). Ensure Start Command uses `$PORT` and `--host 0.0.0.0`. |
| **CORS errors** | Set `ALLOWED_ORIGINS` to your frontend URL(s), comma-separated, no trailing slashes. |
| **Cold starts** | Normal on free tier. Consider a paid instance or a cron ping to `/health` if you need faster first response. |

---

## Quick Checklist

- [ ] Render account + repo connected  
- [ ] PostgreSQL created (free) and **Internal Database URL** available  
- [ ] Web Service created (Python 3, Free instance)  
- [ ] Build: `pip install -r requirements.txt`  
- [ ] Start: `alembic upgrade head && python -m uvicorn main:app --host 0.0.0.0 --port $PORT`  
- [ ] Env: `ENV=PROD`, `DATABASE_URL`, `JWT_SECRET`, `ENCRYPTION_KEY`, `WEBHOOK_BASE_URL`, `ALLOWED_ORIGINS`  
- [ ] `/health` returns `"status":"ok"` and `"db":"ok"`  
- [ ] Shopify/frontend URLs updated to the new API URL  

For more detail on env vars and features (webhooks, profit, shipments, etc.), see **DEPLOYMENT_NOTES.md**.
