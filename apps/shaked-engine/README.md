# Shaked Engine

The Shakdan product: a B2B system that screens parcels for the Shaked Alternative
(Amendment 139) and delivers opportunity dossiers to real-estate developers. Everything the
app needs lives in `apps/shaked-engine/`.

See [PRODUCT_STRUCTURE.md](./PRODUCT_STRUCTURE.md) for the map of what exists and what is next,
and [DEMO.md](./DEMO.md) (Hebrew) for the demo script.

## What the customer does

1. **Draws an area** on the map (up to 250 dunam, inside the city boundary).
2. Optionally sets **mandatory conditions** (minimum lot area, existing units, floors, 400%
   ceiling) and an explicit **preference order**.
3. Presses **Search** and sees counts only — how many candidates were found and how many
   dossiers they will receive. The customer never sees the candidate list.
4. **Accepts** and receives up to `min(3, credits)` dossiers: ready parcels first, then
   parcels whose building file is fetched from the municipal archive on demand. A parcel that
   cannot be completed is skipped and not charged.
5. Opens a **dossier**: §70A gates with citations, evidence per field, the feasibility
   scenario against a 16% minimum developer profit, the betterment levy ceiling and estimate,
   a unit-mix screen, and open gaps. Exports to **PDF** and to **Excel** with live formulas.

Credits are granted by an admin after payment outside the site (`/admin`).

## Stack

- **Backend:** Python 3.12, FastAPI, PostgreSQL + PostGIS, FastAPI-Users (JWT), a Postgres
  `FOR UPDATE SKIP LOCKED` job queue.
- **Frontend:** Next.js (App Router) + react-leaflet. The browser talks to one origin: Next
  proxies `/api/*` to the backend.
- **Sources:** municipal and national GIS layers (seeded from `POC/layer_a/data`), GovMap
  comparable sales, and the municipal building archive — fetched one file at a time on a
  customer's request, never swept (see `POC/layer_a/data/DATA_LAW.md`).

## Run locally

Verified on macOS (13.09.2026) and on Windows 11 with a local Postgres (15.09.2026).

### Database

Either Docker:

```bash
cd apps/shaked-engine
docker compose up -d db
```

or a local PostgreSQL with PostGIS (macOS: `brew install postgresql@17 postgis`), once:

```bash
psql -d postgres -c "CREATE ROLE shaked LOGIN PASSWORD 'shaked' SUPERUSER"
psql -d postgres -c "CREATE DATABASE shaked_engine OWNER shaked"
psql -d shaked_engine -c "CREATE EXTENSION IF NOT EXISTS postgis"
```

If your `shaked` role cannot create databases, create the test database yourself, or 113
tests skip silently:

```bash
createdb -U postgres -O shaked shaked_engine_test
psql -U postgres -d shaked_engine_test -c "CREATE EXTENSION postgis"
```

### Backend

```bash
cd apps/shaked-engine/backend
# --seed matters: without it the venv has no pip of its own, and `pip install` silently
# installs into the system Python instead.
uv venv --python 3.12 --seed .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
cp .env.example .env                                # set a fixed JWT_SECRET
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cities.herzliya.seed_layer_a   # 699 Herzliya parcels + assessment
.venv/bin/python -m pytest -q
.venv/bin/uvicorn app.main:app --port 8000
```

On Windows use `.venv\Scripts\python` (and `.venv\Scripts\alembic.exe`) instead of `.venv/bin/...`.

### Frontend

```bash
cd apps/shaked-engine/frontend
npm install
npx next dev -p 3000
```

Open http://localhost:3000. On `localhost` the app signs in automatically as the development
user; any other address (a LAN IP or a tunnel) shows the login screen.

### Users, credits and the demo company

- **Sign up** at `/signup` — it creates a company whose owner is the new user, with no credits.
- **Make an admin** (grants credits at `/admin`):
  `.venv/bin/python scripts/make_admin.py you@example.com --apply`
- **Create the demo company** on a fresh database (the password is prompted, never printed):
  `.venv/bin/python scripts/demo_setup.py --apply`
- **Before a demo:** `.venv/bin/python scripts/demo_preflight.py` (0 = ready, 1 = warnings,
  2 = do not start). **After a rehearsal:** `.venv/bin/python scripts/demo_reset.py --apply`.

## Checks

| Command (from `backend/`) | What it guards |
|---|---|
| `.venv/bin/python -m pytest -q` | The full suite |
| `.venv/bin/python scripts/check_surfaces.py` | Screen, PDF and Excel show the same numbers on every parcel |
| `.venv/bin/python tests/mutations.py "$(pwd)/.venv/bin/python"` | The tests fail when key rules are broken |
| `.venv/bin/python scripts/audit_db.py` | Data-quality findings in the seeded database |
| `npx tsc --noEmit` (from `frontend/`) | Frontend types |

## Source freshness

`SOURCE_MAX_AGE_DAYS = 30`. A field whose source was fetched more than 30 days ago **stops
deciding gates silently** — no error, candidates simply stop qualifying. The seeded layers were
fetched on 12–13.09.2026 and expire around 12.10. Re-run
`POC/layer_a/scripts/fetch_sources.py` and then the seeder; `evidence_store.stale_fields()`
lists the fields that would otherwise decide.

## If the environment behaves oddly

The symptom: `pip install` reports success and `import` fails.

```bash
.venv/bin/python --version
.venv/bin/pip --version        # must belong to the same interpreter
```

`tests/test_environment.py` enforces this and prints the fix. Rebuilding takes seconds:

```bash
rm -rf .venv && uv venv --python 3.12 --seed .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
```

## Layout

```
apps/shaked-engine/
├── backend/
│   ├── app/
│   │   ├── api/v1/            # routers: candidates (scan), dossiers, account, admin, unit-mix
│   │   ├── cities/herzliya/   # rights chain, assessment, dossier, exports, seeding, prices by block
│   │   ├── services/          # economic (Report 0, betterment), market_data, unit_mix, deliveries
│   │   ├── sources/           # paced HTTP clients for public sources and the archive
│   │   ├── models/            # SQLAlchemy models
│   │   └── core/              # config, database, auth, queue
│   ├── alembic/               # migrations
│   ├── scripts/               # demo_setup / preflight / reset, check_surfaces, audit_db, make_admin
│   └── tests/
├── frontend/                  # Next.js + react-leaflet
├── DEMO.md                    # demo script (Hebrew)
├── PRODUCT_STRUCTURE.md
└── docker-compose.yml         # local Postgres + PostGIS
```
