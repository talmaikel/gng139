# Shaked Engine — Product Structure

Living document. Update this whenever a module is added, a stub is filled in, or
an architectural decision changes. This is the map of the product, not a
changelog — keep it current, not chronological.

Last updated: 2026-09-11 (POC port, phase 1: per-field evidence, public-data client, ITM geometry, first backend tests)

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
- Frontend fixes (package.json, next.config.js, package-lock.json,
  next-env.d.ts) are committed and pushed (`effe626`).
- Tested the dossier task-queue mechanism end-to-end: `POST
  /dossiers/{id}/generate` → row lands `pending` in `task_queue` → worker
  (`python -m app.worker`) claims it via `FOR UPDATE SKIP LOCKED` → marks it
  `done` with the handler's result → `GET /dossiers/status/{task_id}`
  reflects it. **This only proves the queue plumbing works** — the handler
  itself (`generate_dossier_handler` in `worker.py`) is still the documented
  placeholder that returns `{"dossier": "not_yet_implemented"}`; the real
  scraper→preprocessor→extractor→economic-calculator pipeline (known gap #1)
  is still unwired.
- Found and fixed a real bug surfaced by that test: `VerificationLevel`,
  `ReservationStatus`, and `TaskStatus` are all `class X(str, enum.Enum)`
  with lowercase values, but SQLAlchemy's `Enum(X, name=...)` column type
  defaults to binding the member's uppercase `.name` (e.g. `"PENDING"`)
  instead of its lowercase `.value` (`"pending"`) — every ORM-level write
  through these three enum columns would have thrown
  `InvalidTextRepresentationError` against the Postgres enum type. Fixed in
  `app/models/task_queue.py`, `opportunity.py`, and `package.py` by adding
  `values_callable=lambda enum_cls: [m.value for m in enum_cls]` to each
  `Enum(...)` declaration. **Not yet committed/pushed.**
- **Wired the dossier pipeline to real infrastructure and tested it live**
  (see the new "Dossier pipeline" section below for details). Along the way,
  installed Tesseract-OCR 5.5.3 (`heb`+`eng` data) natively on this machine
  and pointed `.env`'s `TESSERACT_CMD` at it (the checked-in default was a
  Linux path); added `pymupdf` to rasterize scraped PDFs for OCR; and fixed
  a real bug in `preprocessor.py` — `cv2.HoughLinesP`'s output shape changed
  between OpenCV versions (`(N,1,4)` vs `(N,4)`), and the installed OpenCV
  5.0.0 uses the new shape, so the old indexing crashed on every real image.

### macOS (Boaz)

- **PostgreSQL 17.11 + PostGIS 3.6.4 via Homebrew**, not 16 as on the Windows
  machine: Homebrew's PostGIS is built only for Postgres 17 and 18. Nothing the
  Engine uses differs between 16 and 17 (PostGIS geometry, GiST, partial unique
  index, `SKIP LOCKED`, enums); flag any 17-only feature in review.
- Started with `pg_ctl` (not a login service). Role `shaked`/`shaked`, database
  `shaked_engine`, `postgis` extension created by the superuser beforehand
  because the migration role cannot create it.
- `alembic upgrade head` → `0002_field_evidence`; downgrade to `0001` and
  upgrade again verified clean.

## Dossier pipeline (live-tested, not just wired)

`backend/app/worker.py`'s `generate_dossier_handler` now really calls:
DB lookup → municipal archive → PDF rasterize → OpenCV preprocess → OCR
extract → economic calculator, and returns the assembled result as the
task's `result` JSON. This was tested against the **real, live** Herzliya
municipal systems, not mocks:

- **Herzliya's real archive turned out to be a plain HTTP GET API**
  (`https://handasi.complot.co.il/magicscripts/mgrqispi.dll`, legacy
  CGI-style query params), not a JS-rendered page — so
  `backend/app/cities/herzliya/archive_client.py` (`HerzliyaArchiveClient`)
  talks to it directly with `httpx`, no browser needed. Confirmed live: gush
  6424 / parcel 83 → real tik (building-file) id `1652`, matching a
  known-good record from `POC/data/pilot-batch-01/manifest.csv`.
  `backend/app/pipeline/scraper.py`'s Playwright scaffold is kept as the
  fallback path for a city whose real archive does require a browser (Tel
  Aviv's isn't confirmed either way yet).
- **Important real-world finding**: the archive's `GetTikDocs` endpoint
  (used to list a tik's attached PDFs) is real and correctly implemented,
  but returns **zero results for pre-1970s tik files** — verified against
  all three known-good addresses in `manifest.csv` (gush/parcel 6424/83,
  6538/206, 6546/271). Those old scans live only on a separate legacy system
  (`archive.gis-net.co.il`, e.g.
  `.../archiv/1950-1969/19610028/19610028_20.pdf`), keyed by permit
  *request* number rather than tik number — I have not found/enumerated the
  lookup that maps a tik to its request numbers on that system. This is a
  real gap for older addresses, not a code bug; newer digitized tiks may
  well have documents attached via `GetTikDocs` — untested, since none of
  the three known addresses are recent.
- **OCR path independently validated against a real 1961 scanned permit
  form** (downloaded directly from the `archive.gis-net.co.il` URL above,
  bypassing the empty `GetTikDocs` step, purely to prove the pipeline code
  works on genuine data): `preprocess_blueprint` ran real CLAHE contrast +
  Otsu binarization + Hough-line legend cropping (this is where the OpenCV
  5.0 shape bug was found and fixed); local Tesseract OCR ran for real
  (`heb+eng`) at confidence 61 — just above the 60 threshold — but found no
  regex-matching area field on this heavily handwritten cursive-Hebrew
  1960s form, so the code correctly fell through to the OpenAI fallback
  path.
- **AI fallback path since tested for real with a live `OPENAI_API_KEY`**,
  against the same 1961 scan. Found and fixed a real bug first: OpenAI's
  strict structured-output mode requires *every* schema property to be
  listed in `required`, including nullable ones — `EXTRACTION_JSON_SCHEMA`
  in `extractor.py` only required 2 of its 4 properties, so every call
  failed with a 400 until fixed. After the fix, `gpt-4o-mini` returned a
  well-formed result (`total_building_area_sqm: 128`, `confidence: 0.9`).
  **The number is very likely wrong**: comparing against the actual form,
  128 is almost certainly the plot/lot number (`מגרש מס' 128`, "Plot No.
  128"), not a building area — the model appears to have misread a label
  as a measurement, confidently. The form's real building area isn't
  cleanly printed at all; it would need to be derived from `שטח המגרש
  ~750.2` (plot area) × a handwritten building-coverage percentage, which
  the model didn't attempt. **This is a real, honest finding, not a wiring
  problem**: it's exactly why `verification_level` distinguishes
  `ai_assisted` from `human_verified` — an AI-extracted figure on a messy
  historical scan needs human review before being treated as ground truth.
  Nothing in the pipeline currently flags "this AI answer looks
  suspicious" — that's a real gap (see known gaps).
- **AI plausibility check implemented and live-tested against the same
  case.** `extractor.py` now has `_check_plausibility(area, plot_area_sqm)`:
  a bounds check (20–5000 sqm, and at most 3x the plot area) applied to
  *every* extraction, local or AI. Verified it correctly rejects grossly
  wrong values (a gush number, a value 4x the plot area, etc.) — but, as
  expected, it does **not** catch the 128-sqm plot-number misread above,
  since 128 is a perfectly normal building size for a 750 sqm plot. That
  confirms the bounds check alone was never going to be the real fix.
  The actual fix is policy, not math: `ExtractionResult.requires_human_review`
  is unconditionally `True` for every AI-fallback result regardless of
  plausibility, and `worker.py`'s `generate_dossier_handler` now only feeds
  the economic calculator a *local*-OCR figure that passed the bounds
  check; an AI-derived figure is used only as a last resort before the
  plot-area estimate, and always labeled
  `feasibility_assumptions.buildable_area_source = "ai_assisted_unverified"`
  with a dossier-level `requires_human_review: true` flag. Re-ran the exact
  128-sqm case through the real `generate_dossier_handler` (real OCR, real
  OpenAI call, real economic calculator) and confirmed the dossier now
  correctly surfaces both flags instead of silently using 128 as fact.
- **Full queue run tested live**: enqueued a dossier job for a real
  opportunity (gush 6424/parcel 83, plot area 750.2 sqm — the real figure
  read off the scanned form), worker claimed it via `SKIP LOCKED`, made the
  real archive call, correctly found 0 attached documents, fell back to an
  estimated buildable area (`plot_area_sqm * 0.6`), ran the real economic
  calculator, and returned a complete result via `GET
  /dossiers/status/{task_id}`.
- **Feasibility assumptions are still hardcoded placeholders**
  (`DEFAULT_SALE_PRICE_PER_SQM_ILS`, `DEFAULT_CONSTRUCTION_COST_PER_SQM_ILS`,
  `DEFAULT_EXISTING_UNITS` in `worker.py`) — no per-city/per-opportunity
  source for these exists yet. The dossier result labels them clearly
  (`feasibility_assumptions`) rather than presenting them as real numbers.
- **Not yet committed/pushed**: `worker.py`, `archive_client.py`,
  `preprocessor.py` fix, `requirements.txt` (`pymupdf`), `.env.example`
  (Tesseract path comment).

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
| Herzliya archive client | `backend/app/cities/herzliya/archive_client.py` | ✅ | Live-tested `httpx` client for the real `handasi.complot.co.il` permit-file API — see "Dossier pipeline" section |
| Tel Aviv strategy | `backend/app/cities/tel_aviv/` | 🚧 | Stub only — proves the pattern, every method raises `NotImplementedError` |
| Economic calculator ("Generic Report 0") | `backend/app/services/economic/calculator.py` | ✅ | Pure Python, no Excel. Tenant/developer sqm split is a simplified 1:1-replacement model — validate against the real PRD formula before relying on it |
| Scraper (generic/JS fallback) | `backend/app/pipeline/scraper.py` | 🚧 | Playwright scaffolding for a city whose real archive needs browser rendering. Herzliya turned out not to need this — see `archive_client.py` |
| Preprocessor | `backend/app/pipeline/preprocessor.py` | ✅ | OpenCV: CLAHE contrast + Otsu binarization + Hough-line legend-region crop. Live-tested on a real 1961 scan |
| Extractor | `backend/app/pipeline/extractor.py` | ✅ | Tesseract (heb+eng) + regex first; falls back to OpenAI `gpt-4o-mini` structured output below a confidence threshold. Both paths run every result through `_check_plausibility` (bounds check) and mark AI-fallback results `requires_human_review=True` unconditionally — live-tested, see "Dossier pipeline" section |
| Dossier generation | `backend/app/worker.py` (`generate_dossier_handler`) | ✅ | Real orchestration: DB → archive client → rasterize → preprocess → extract → economic calculator. Live-tested end-to-end via the queue — see "Dossier pipeline" section for what was and wasn't fully exercised |
| API routers | `backend/app/api/v1/` | ✅ | `auth`, `candidates` (+ unify), `filters`, `dossiers` (generate + status), `economic` (feasibility) |
| DB migrations | `backend/alembic/versions/` | ✅ | `0001`: tenants, users, opportunities (+PostGIS/GiST index), packages, balances, reservations (+ partial-unique active-lock index), task_queue. `0002`: field_evidence + `evidence_certainty` enum (upgrade/downgrade/upgrade verified on Postgres 17) |
| Per-field evidence | `backend/app/evidence.py`, `backend/app/models/evidence.py` | ✅ | Ported from `POC/app/rules.py`. One observation per row (value, source URL, retrieval time, SHA-256, location, method, certainty). `resolve_evidence` keeps disagreeing sources as a conflict instead of overwriting; `usable` lets only official/derived/manually-verified, sourced, located evidence under 30 days old decide a check. OCR and AI readings are `ocr_candidate` / `ai_candidate` and never decide until a person verifies them |
| Public-data client | `backend/app/sources/client.py` | ✅ | Async rewrite of `POC/app/sources.py` `PublicClient`: on-disk cache that keeps the original retrieval time and hash, replayable URLs, retry on 429/5xx honouring `Retry-After`, HTML-with-200 rejected as JSON, 25 MB cap, per-host pacing (archive 10 s; Overpass 15 s backoff). Connectors (GovMap, ArcGIS, Overpass, archive) move onto it in phase 2 |
| Geometry (ITM) | `backend/app/geo.py` | ✅ | Ported from `POC/app/geo.py`: EPSG:2039 ↔ 4326, search-area validation against the official boundary, building→parcel attribution by overlap share (not nearest neighbour), verified parcel pairing |
| Backend tests | `backend/tests/` | ✅ | 30 tests: POC tests for the ported modules, assertions unchanged, plus new ones for the async client and the evidence table. `test_evidence_db.py` runs against a migrated Postgres in a rolled-back transaction and skips when none is reachable. Run: `pip install -r requirements-dev.txt && pytest` |
| Frontend auth | `frontend/src/app/login/page.tsx` | ✅ | Calls `/api/v1/auth/jwt/login`, stores JWT in `localStorage` |
| Frontend map | `frontend/src/components/Map.tsx` | ✅ | react-leaflet: renders each candidate's real parcel polygon (not just a point marker), auto-fits bounds to whatever's loaded, popup with address/block/parcel/area. Browser-verified against two real parcels |
| Frontend dashboard | `frontend/src/app/dashboard/page.tsx` | ✅ | Lists candidates in a table and now actually passes them to the map (previously fetched `candidates` but never passed them to `<OpportunityMap>` at all — a real disconnect, now fixed) |

## Data model (see `backend/alembic/versions/0001_initial_schema.py` for the source of truth)

- **tenants** — companies (the paying customers)
- **users** — FastAPI-Users compatible, `company_id` FK scopes every query
- **opportunities** — GIS parcels (PostGIS `MULTIPOLYGON`), XPlan code, verification level, freeform `metadata_json` (holds the XPlan screening `category`/`tags`)
- **packages** — purchasable credit bundles
- **balances** — remaining credits per tenant
- **reservations** — competitive lock on one opportunity; **only one `active` reservation may exist per `opportunity_id`** (partial unique index) — this is the mechanism that prevents the same parcel being served to two competing tenants at once
- **task_queue** — async job rows for the `SKIP LOCKED` worker
- **field_evidence** — one row per observed value of one field of one opportunity, with its source URL, retrieval time, SHA-256, location in the source, method and certainty. Several rows per field are expected; they are resolved in code, so a conflict between sources is kept rather than overwritten

## Known gaps / next steps

1. **Older Herzliya permit scans (pre-1970s) aren't reachable yet.** Their
   PDFs live on `archive.gis-net.co.il` keyed by permit *request* number, not
   tik number, and no live enumeration from tik → request numbers has been
   found. Newer/digitized tiks may work via `GetTikDocs` already — untested.
2. ~~The AI fallback has no plausibility/confidence check on its own
   answer.~~ **Done.** `extractor.py._check_plausibility` bounds-checks
   every extraction; every AI-fallback result is unconditionally flagged
   `requires_human_review`; `worker.py` only trusts local-OCR figures for
   the calculator and labels an AI-derived one
   `buildable_area_source: "ai_assisted_unverified"` with a dossier-level
   `requires_human_review: true`. **Not yet committed/pushed.** Remaining
   related gap: `Opportunity.verification_level` (the DB column) is never
   actually updated by any of this — the new flags exist only in the
   per-dossier JSON result, not persisted against the opportunity itself.
   There's also no UI/workflow yet for a human to act on
   `requires_human_review` — it's surfaced in the data, not consumed
   anywhere.
3. ~~Candidates API doesn't expose geometry, so the frontend map has no real
   markers.~~ **Done.** `screen_herzliya_candidates` now returns `geometry`
   (GeoJSON `MultiPolygon`, via `ST_AsGeoJSON`) and `centroid` (`{lat, lng}`,
   via `ST_Centroid`/`ST_X`/`ST_Y`) per candidate, computed in PostGIS rather
   than pulling geometry into Python. `Map.tsx` now renders each candidate's
   real parcel polygon (not just a point) and auto-fits the map to whatever's
   loaded. Also fixed a real disconnect while wiring this up:
   `dashboard/page.tsx` was fetching `candidates` but never actually passing
   them to `<OpportunityMap>` — the map has been dead code since the
   bootstrap commit. Browser-verified against two real inserted parcels:
   both polygons render at the correct location, popup shows correct
   address/block/parcel/area, zero console errors. **Not yet
   committed/pushed.**
4. **Economic calculator's tenant/developer sqm split is simplified** (1:1
   replacement + flat compensation sqm), and `worker.py`'s market assumptions
   (sale price, construction cost, existing units) are hardcoded placeholders
   with no per-city/per-opportunity source. Validate against the actual Shaked
   PRD formula (Generic Report 0) before using either for real numbers.
5. **Tel Aviv is unimplemented** — proves the strategy pattern, nothing more.
   Unknown whether its real archive is an API (like Herzliya) or needs the
   Playwright scraper scaffold.
6. **Test coverage is partial.** `backend/tests/` covers the modules ported in
   phase 1 (30 tests). Older backend modules (queue, cities, pipeline, worker,
   API) and the whole `frontend/` still have none.
7. **Reservation expiry isn't enforced anywhere** — the `expires_at` column
   exists but nothing currently sweeps/releases expired locks back to
   `released` status.
