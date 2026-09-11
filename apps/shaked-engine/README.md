# Shaked Engine

B2B PropTech system for screening and packaging urban-renewal opportunities under
the "Shaked Alternative" (חלופת שקד). Isolated inside this monorepo at
`apps/shaked-engine/` — nothing outside this directory is touched by this app.

See [PRODUCT_STRUCTURE.md](./PRODUCT_STRUCTURE.md) for the living map of what
exists, what's stubbed, and what's next.

## Stack

- **Backend**: Python 3.11+, FastAPI, PostgreSQL + PostGIS, FastAPI-Users (JWT), a
  pure-Postgres `FOR UPDATE SKIP LOCKED` job queue (no Redis/RabbitMQ).
- **Frontend**: Next.js (App Router) + react-leaflet.
- **Pipeline**: Playwright (scraping) → OpenCV (pre-processing) → Tesseract OCR
  with an OpenAI `gpt-4o-mini` structured-output fallback (extraction).

## Local setup

```bash
# 1. Database (Postgres + PostGIS)
cd apps/shaked-engine
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # or `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
copy .env.example .env   # or `cp` on macOS/Linux — fill in secrets
alembic upgrade head
uvicorn app.main:app --reload

# 3. Background worker (separate terminal)
python -m app.worker

# 4. Frontend (separate terminal)
cd ../frontend
npm install
copy .env.example .env.local
npm run dev
```

Backend: http://localhost:8000/health · Frontend: http://localhost:3000

## Repo layout

```
apps/shaked-engine/
├── backend/
│   ├── app/
│   │   ├── core/         # config, DB session, auth (FastAPI-Users), Postgres queue worker
│   │   ├── cities/        # strategy pattern: base.py + herzliya/, tel_aviv/ (stub)
│   │   ├── services/economic/  # feasibility calculator ("Generic Report 0")
│   │   ├── pipeline/      # scraper.py, preprocessor.py, extractor.py
│   │   ├── models/        # SQLAlchemy models
│   │   ├── api/v1/        # routers
│   │   └── main.py
│   └── alembic/           # migrations
├── frontend/               # Next.js + react-leaflet
└── docker-compose.yml      # local Postgres+PostGIS
```
