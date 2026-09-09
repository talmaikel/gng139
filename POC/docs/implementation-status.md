# Implementation status

## Implemented and tested

- Local FastAPI application, Hebrew RTL UI, real Leaflet map and polygon input.
- Live GovMap boundary and parcel collection, CRS transforms, discovery and schema checks.
- Municipal service discovery with explicit failures and community-footprint fallback.
- Public archive HTML search and extraction of source tables; document collection hooks, native PDF text and optional OCR.
- Saved source evidence, snapshot dossiers, source matrix, critical missing-data gates, ordered filtering/ranking.
- Background scans, persistent partial progress and restart recovery.
- Simulated company entitlement, atomic delivery accounting and deduplication.
- Draft PDF and Excel exports; scenario calculation API gated on planning evidence.
- Targeted Shoshanim 4 importer: municipal archive identity, four archive documents, current parcel, planning context, source hashes and deterministic dossier.
- 25 automated tests passed. Browser audit and live-scan flow exercised. Exported PDF pages rendered and visually inspected.

## Live end-to-end result

On 7 September 2026, the browser-created pilot scan completed with **39 buildings and 91 official parcels**. It collected **5 archive-file associations**, then the archive returned 429 during document listing. The collector stopped further archive calls for that job. It produced **39 needs-verification dossiers, zero ready deliveries**, and retained all three simulated entitlements.

The separately preserved ten-building source audit remains available in the UI. These are actual retrieved records, not generated demo properties.

The targeted Shoshanim 4 experiment subsequently populated one real dossier from the uploaded permit and municipal archive. It passes six of six building-level threshold checks and contains a conservative preliminary rights ceiling. Its status remains needs-verification because TAMA 70 and the strategic-renewal classification must be resolved before the result can support delivery or a financial scenario.

## Not complete

- Automatic original-permit discovery and extraction are not yet reliable at area scale. They were completed and verified manually for Shoshanim 4.
- Planning-lot geometry, exhaustive applicable-plan checks and a supported property-specific scenario basis remain missing. Merely having a plan-number table does not satisfy these checks.
- Current collectors consequently have no validated path to a ready dossier. Their discovery output is intentionally incomplete; all-ready delivery was tested with explicitly synthetic test fixtures only.
- The policy engine performs partial, conservative screening from the municipal document. It is not a validated complete legal rule bundle.
- Parcel-pair geometry is implemented/tested; pair opportunity construction and delivery are disabled pending the required evidence.
- Financial assumptions are not approved. The calculation API and spreadsheet formula structure exist, but no real candidate has a complete financial scenario. The UI shows that blocker.
- PostgreSQL/PostGIS configuration and adapter are provided but not executed on this host. Local verification used SQLite and Shapely/PROJ. Docker includes Hebrew OCR; live Hebrew scanned-permit OCR has not been validated here.
- Browser automation for additional public sources has not been built because the verified archive already exposes public HTML queries. A source-specific browser connector remains future work if needed.

The remaining work is a mixture of connector/extraction development, authoritative-source access, rule validation and approved financial assumptions. No claim of three saleable opportunities is made.
