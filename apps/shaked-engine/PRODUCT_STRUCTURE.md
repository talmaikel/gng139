# Shaked Engine — Product Structure

Public overview of the application structure. Implementation details remain in
the source code and migrations, which are the source of truth.

Last updated: 2026-09-14

## Product scope

Shaked Engine is a B2B PropTech application for screening and packaging urban
renewal opportunities under Israel's Shaked Alternative (חלופת שקד). The first
supported city is Herzliya.

The main user flow is:

1. Define a search area and screening preferences.
2. Review ranked parcel opportunities.
3. Select up to three opportunities for deeper analysis.
4. Generate an auditable dossier with planning, source and economic data.

## Application structure

| Area | Location | Purpose |
|---|---|---|
| Backend API | `backend/app/api/` | Authentication, candidates, filters, dossiers and feasibility endpoints |
| City rules | `backend/app/cities/` | City-specific screening and archive integrations behind shared interfaces |
| Evidence | `backend/app/evidence.py`, `backend/app/models/evidence.py` | Source, retrieval time and certainty for observed fields |
| Geometry | `backend/app/geo.py` | Israeli-grid conversion and parcel/building spatial operations |
| Document pipeline | `backend/app/pipeline/` | PDF processing, OCR and structured extraction |
| Dwelling units | `backend/app/models/dwelling_unit.py`, `backend/app/services/dwelling_units.py` | Per-apartment permitted areas with provenance, certainty and review gates |
| Economic service | `backend/app/services/economic/` | Versioned assumptions and feasibility calculations |
| Market-data service | `backend/app/services/market_data/` | On-demand comparable sales and room-level price estimates |
| Background worker | `backend/app/worker.py` | Dossier generation outside the request cycle |
| Database migrations | `backend/alembic/versions/` | Versioned PostgreSQL/PostGIS schema |
| Frontend | `frontend/src/` | Login, dashboard, filters and opportunity map |

## Dossier pipeline

The dossier worker combines the selected opportunity with available planning
documents, extracted building information, versioned economic assumptions and
local comparable sales. Missing required planning inputs remain explicit and
block a completed feasibility result; they are not silently replaced by facts.

AI-assisted document extraction is treated as reviewable evidence. Source
records, derived values and calculation assumptions retain their status so a
consumer can distinguish data from estimates.

When a permit contains a labelled apartment schedule, the worker stores one
row per dwelling unit. Unreviewed OCR/AI readings may be displayed but cannot
make a dossier deliverable; a complete manually confirmed schedule may drive
the existing-unit average and per-household allocation. If no schedule is
available, a footprint-based average remains an explicit non-deciding estimate.

Current limitation: the extractor records each unit's permitted total area and
floor, but does not yet split principal area from service area, and there is no
review endpoint/UI that can turn a candidate row into a manually confirmed
row. Accordingly, this is B3 groundwork rather than completion of B3.

## Comparable-sales pipeline

Comparable sales are acquired only after the user selects the final one to
three opportunities. This keeps the broad screening stage lightweight and
limits calls to the public upstream source.

Default valuation parameters are:

- 12-month lookback period.
- 500-metre radius from the opportunity centroid.
- Separate estimates for 3-, 4- and 5-room apartments.
- Apartment, date, distance and plausibility filters before calculation.
- Price-per-square-metre outlier handling.
- Median, range, sample size and confidence for each room group.

The service stores two different record types:

- Source transactions are upserted by source and deal identifier. They remain
  dated historical facts.
- Valuation runs are immutable snapshots containing the exact date, radius,
  lookback period and unit-mix parameters used for the calculation.

A parameter-aware cache avoids repeating the same acquisition during its
configured freshness period. When prices or inputs change, a later valuation
creates a new snapshot instead of overwriting the earlier result.

The feasibility calculator uses a blended local sale price only when the
opportunity contains an explicit and complete `planned_unit_mix`. Without that
mix, the dossier exposes the room-level estimates but keeps the versioned city
assumption as the project-level fallback.

The current public transaction source does not provide a documented commercial
service-level guarantee. The integration is isolated behind the market-data
service so it can be replaced by a licensed provider without changing the
valuation logic.

## Data model

The principal entities are:

- `tenants` and `users` for company-scoped access.
- `opportunities` and `buildings` for parcel and building identity.
- `field_evidence` for sourced observations and certainty.
- `dwelling_units` for per-apartment permitted areas, provenance and review
  status.
- `packages`, `balances`, `reservations` and `deliveries` for the commercial
  workflow.
- `task_queue` for asynchronous work.
- `property_transactions` for factual comparable-sale records.
- `market_valuation_runs` for dated calculation snapshots.

Migration `0007_add_market_data` adds the two market-data tables after the
delivery-ledger migration. Migration `0008_dwelling_units` then adds the
per-apartment table without creating a second Alembic head.

## Verification

The backend test suite covers the market-data coordinate conversion, upstream
record filtering, room segmentation, outlier handling, explicit-unit-mix
blending, concurrency-safe transaction upserts and the dwelling-unit decision
rules. Database-backed tests run when a compatible test database is available.

Before production use, market-source terms, valuation methodology and material
commercial assumptions should be reviewed by the appropriate professional.
