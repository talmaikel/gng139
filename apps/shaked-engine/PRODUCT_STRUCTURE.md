# Shaked Engine — Product Structure

Living document. Update this whenever a module is added, a stub is filled in, or
an architectural decision changes. This is the map of the product, not a
changelog — keep it current, not chronological.

Last updated: 2026-09-11 (local DB stood up, migration applied)

## Local environment status

- PostgreSQL 16 + PostGIS 3.6.2 installed natively on this Windows machine
  (no Docker — `docker-compose.yml` is still the documented path for other
  environments, but wasn't used here since Docker wasn't installed). Service
  `postgresql-x64-16`, port 5432, superuser `postgres`/`shaked`.
- `shaked` role + `shaked_engine` database created, owned by `shaked`.
- `backend/.venv` created, full `requirements.txt` installed (Python 3.14).
  Had to add `psycopg2-binary` (missing sync driver for Alembic — asyncpg only
  covers the app's async engine).
- `alembic upgrade head` applied successfully — all 8 tables + the GiST/partial
  indexes exist. Fixed a real bug in `0001_initial_schema.py` along the way:
  the three `postgresql.ENUM` types were being created twice (once via the
  manual `.create(checkfirst=True)` call, once implicitly by `create_table`'s
  DDL events) — added `create_type=False` to each `ENUM(...)` declaration.
- Backend boots with `uvicorn app.main:app` and verified end-to-end against
  the real DB: register → JWT login → authenticated `filters/options`,
  `economic/feasibility`, and `candidates/herzliya` all return correctly;
  unauthenticated requests correctly get 401 instead of crashing.
- Frontend: `npm install` on the original pinned `next@14.2.5` surfaced a
  **critical** vulnerability (multiple advisories up through unauthenticated
  RCE, only fixed at `next@15.5.24+`) — bumped to `next@15.5.25` (kept React
  18, which 15.5.x still supports) and pinned `postcss` to `8.5.28` via an
  `overrides` entry to clear a separate high-severity postcss advisory.
  `npm audit` is now clean.
- Frontend map crashed every mount with "Map container is already
  initialized" — `react-leaflet` v4's `MapContainer` doesn't clean up its
  Leaflet instance correctly under React 18 Strict Mode's dev-only
  double-invoked effects. Fixed by setting `reactStrictMode: false` in
  `next.config.js` (the standard fix for this specific library combo).
  Verified clean in a fresh tab: login → dashboard → map renders, zero
  console errors, `candidates/herzliya` call succeeds.
- These frontend fixes (package.json, next.config.js) are **not yet
  committed/pushed** — only applied locally during verification.

## What this is

A B2B PropTech system that screens, packages, and sells urban-renewal
opportunities under Israel's "Shaked Alternative" (חלופת שקד) — an urban-renewal
exemption track. Tenants (real-estate/development companies) log in, browse
pre-screened candidate parcels for a city, reserve one (locking out competitors),
and generate a dossier (legal/planning/financial package) for it.

Related prior art in this monorepo (not a dependency of this app — read for
domain context only, per the isolation rule):
- `POC/app/xplan.py` — the original Herzliya XPlan screening logic. This app's
  `backend/app/cities/herzliya/xplan_schema.py` mirrors its mavat_code /
  category vocabulary (`primary_candidate`, `needs_verification`,
  `filtered_landuse`, `preservation`, `existing_renewal_plan`, `metro`,
  `urban_renewal_compound`) so the two stay conceptually aligned.
- `POC/PRD_Shaked_Herzliya_v2.docx` — the PRD this bootstrap was built from.

## Status legend

- ✅ Implemented (boilerplate/scaffold-complete, not battle-tested)
- 🚧 Stubbed (interface exists, raises `NotImplementedError` or is a placeholder)
- ❌ Not started

## Module map

| Module | Path | Status | Notes |
|---|---|---|---|
| Config / DB session | `backend/app/core/config.py`, `database.py` | ✅ | Pydantic settings, async SQLAlchemy engine |
| Auth / multi-tenancy | `backend/app/core/security.py`, `schemas.py` | ✅ | FastAPI-Users JWT; `User.company_id` scopes every user to a `Company` tenant |
| Postgres job queue | `backend/app/core/queue.py` | ✅ | `FOR UPDATE SKIP LOCKED` claim; no Redis/RabbitMQ |
| City strategy interface | `backend/app/cities/base.py` | ✅ | `BaseCityRules` ABC: screen_candidates, is_eligible_xplan_code, check_plot_unification, minimum_plot_area_sqm |
| Herzliya strategy | `backend/app/cities/herzliya/` | ✅ | Real XPlan code vocabulary + `ST_Touches`/`ST_Union` unification query. Candidate screening queries real `opportunities` rows — needs real data loaded to be useful |
| Tel Aviv strategy | `backend/app/cities/tel_aviv/` | 🚧 | Stub only — proves the pattern, every method raises `NotImplementedError` |
| Economic calculator ("Generic Report 0") | `backend/app/services/economic/calculator.py` | ✅ | Pure Python, no Excel. Tenant/developer sqm split is a simplified 1:1-replacement model — validate against the real PRD formula before relying on it |
| Scraper | `backend/app/pipeline/scraper.py` | 🚧 | Playwright scaffolding; form selectors are placeholders — wire up the real municipal archive site per city |
| Preprocessor | `backend/app/pipeline/preprocessor.py` | ✅ | OpenCV: CLAHE contrast + Otsu binarization + Hough-line legend-region crop |
| Extractor | `backend/app/pipeline/extractor.py` | ✅ | Tesseract (heb+eng) + regex first; falls back to OpenAI `gpt-4o-mini` structured output below a confidence threshold |
| Dossier generation | `backend/app/worker.py` (`generate_dossier_handler`) | 🚧 | Placeholder — doesn't yet call the scraper/preprocessor/extractor/economic pipeline end-to-end |
| API routers | `backend/app/api/v1/` | ✅ | `auth`, `candidates` (+ unify), `filters`, `dossiers` (generate + status), `economic` (feasibility) |
| DB migrations | `backend/alembic/versions/0001_initial_schema.py` | ✅ | tenants, users, opportunities (+PostGIS/GiST index), packages, balances, reservations (+ partial-unique active-lock index), task_queue |
| Frontend auth | `frontend/src/app/login/page.tsx` | ✅ | Calls `/api/v1/auth/jwt/login`, stores JWT in `localStorage` |
| Frontend map | `frontend/src/components/Map.tsx` | ✅ | react-leaflet, OSM tiles, centered on Herzliya. Markers need real lat/lng — `candidates` API doesn't expose geometry yet |
| Frontend dashboard | `frontend/src/app/dashboard/page.tsx` | ✅ | Lists candidates for Herzliya in a table; map is not yet wired to real candidate coordinates |

## Data model (see `backend/alembic/versions/0001_initial_schema.py` for the source of truth)

- **tenants** — companies (the paying customers)
- **users** — FastAPI-Users compatible, `company_id` FK scopes every query
- **opportunities** — GIS parcels (PostGIS `MULTIPOLYGON`), XPlan code, verification level, freeform `metadata_json` (holds the XPlan screening `category`/`tags`)
- **packages** — purchasable credit bundles
- **balances** — remaining credits per tenant
- **reservations** — competitive lock on one opportunity; **only one `active` reservation may exist per `opportunity_id`** (partial unique index) — this is the mechanism that prevents the same parcel being served to two competing tenants at once
- **task_queue** — async job rows for the `SKIP LOCKED` worker

## Known gaps / next steps

1. **Dossier pipeline is not wired end-to-end.** `generate_dossier_handler` in
   `backend/app/worker.py` is a placeholder — it needs to call the scraper →
   preprocessor → extractor → economic calculator and assemble a real dossier.
2. **Candidates API doesn't expose geometry**, so the frontend map has no real
   markers yet — either add a `GeoJSON`/lat-lng field to the candidates response
   or fetch geometry separately.
3. **Economic calculator's tenant/developer sqm split is simplified** (1:1
   replacement + flat compensation sqm). Validate it against the actual Shaked
   PRD formula (Generic Report 0) before using it for real numbers.
4. **Scraper selectors are placeholders.** Each municipality's real archive site
   markup needs to be wired in (`backend/app/pipeline/scraper.py`), likely one
   scraper subclass/config per city.
5. **Tel Aviv is unimplemented** — proves the strategy pattern, nothing more.
6. **No tests yet.** Nothing under `backend/` or `frontend/` has automated
   coverage.
7. **Reservation expiry isn't enforced anywhere** — the `expires_at` column
   exists but nothing currently sweeps/releases expired locks back to
   `released` status.
