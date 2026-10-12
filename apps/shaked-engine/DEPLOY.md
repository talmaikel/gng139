# Deploying to Render (free) at gng139.online

What runs where:
- **shaked-web**, the Next.js frontend: a free Node service. It serves `gng139.online` and forwards `/api/*` to the API.
- **shaked-api**, the FastAPI backend: a free Docker service built from `backend/Dockerfile`. It runs `alembic upgrade head` on every start and runs the job worker in the same process (`RUN_WORKER_IN_PROCESS=true`).
- **Database:** Neon free Postgres with PostGIS.

Everything is defined in [`render.yaml`](../../render.yaml) at the repo root.

## 1. Database (Neon)
1. Create a project at neon.tech in an EU region.
2. In the SQL editor, run `CREATE EXTENSION IF NOT EXISTS postgis;`.
3. Copy the connection string and prepare two versions of it:
   - `DATABASE_URL`: `postgresql+asyncpg://USER:PASS@HOST/DB?ssl=require`
   - `DATABASE_URL_SYNC`: `postgresql://USER:PASS@HOST/DB?sslmode=require`

## 2. Render
1. Push `main` to GitHub.
2. In the Render dashboard: **New → Blueprint** → choose the repo.
3. Paste the secrets it asks for: `DATABASE_URL`, `DATABASE_URL_SYNC`, `RESEND_API_KEY`, `OPENAI_API_KEY`, `BRAVE_SEARCH_API_KEY` (W5 automated renewal search — without it, every new renewal check stays `retryable` and the parcel is not delivered).
4. Once `shaked-api` is live, check its URL. If it isn't exactly `https://shaked-api.onrender.com`, update `API_ORIGIN` on `shaked-web` and trigger a redeploy. The rewrite is fixed at build time.

## 3. Seed the data (once, from your machine)
```bash
cd apps/shaked-engine/backend
DATABASE_URL="<asyncpg url>" DATABASE_URL_SYNC="<sync url>" .venv/Scripts/python.exe -X utf8 -m app.cities.herzliya.seed_layer_a
```
Then run `scripts/seed_packages.py` and `scripts/make_admin.py` the same way.

## 4. Domain (Cloudflare → Render)
1. In Render, open **shaked-web → Settings → Custom Domains** and add `gng139.online` and `www.gng139.online`.
2. In Cloudflare DNS, add CNAME records for `@` and `www` pointing to `shaked-web.onrender.com`, set to **DNS only (grey cloud)**.
3. Wait until Render shows the certificate as issued. If you turn on the orange-cloud proxy later, set Cloudflare SSL/TLS to **Full**.

## 5. Email (Resend)
Verify the `gng139.online` domain in Resend by adding its DNS records in Cloudflare. `EMAIL_FROM` already defaults to `no-reply@gng139.online`.

## Free-plan limits
- Both services go to sleep after 15 minutes idle. The first visit afterwards takes 30–60 seconds, and background jobs pause while the service sleeps.
- Each service has 512 MB of RAM. Dossier OCR can run out of memory; if it does, move `shaked-api` to the Starter plan ($7/month).
