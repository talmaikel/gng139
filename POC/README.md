# Shakdan — Herzliya real-data POC

Hebrew, RTL local pilot built from the supplied product demo. Live collection, saved evidence, real map selection, draft dossiers, PDF and Excel exports, simulated entitlement. The original demo is separate at `/demo`.

For a clean Windows setup after cloning or pulling the repository, see the [Hebrew colleague setup guide](docs/colleague-setup-windows.md). It includes the one-command setup script, Edge/Tesseract checks, first-run verification and common fixes.

## Run locally on Windows

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/vendor.py
./start.ps1
```

Open http://127.0.0.1:8000. Use **פתיחת התיק המנותח** to inspect the completed Shoshanim 4 evidence experiment, **פתיחת בדיקת 10 המבנים** for the preserved area audit, or **בחירת אזור לדוגמה** then **סריקת האזור** to collect live data. Live sources require internet access. Basemap tiles are provided by OpenStreetMap; Leaflet code is vendored.

To keep the local server running in the background, run `./start-background.ps1`. It prints the server PID and saves logs under `data`. Stop that process using its printed PID when finished.

## PostgreSQL / PostGIS

```powershell
docker compose up --build
```

Alternatively set `DATABASE_URL` to a PostgreSQL connection string before starting the app. The database user must be able to enable PostGIS during initialization. Spatial entities are stored as geometry in EPSG:2039 with a GiST index. JSON snapshots preserve original evidence. The Docker image includes Hebrew fonts and Tesseract Hebrew/English OCR.

Docker/PostgreSQL are not installed on the development host. The Windows launch therefore uses an explicit SQLite local mode plus Shapely/PROJ for spatial calculations. This is a runnable local fallback, not a PostGIS performance validation. The API reports the active database mode. Use one application process/worker for this POC.

## What works

- WFS discovery and schema checks; official Herzliya boundary and paginated parcel collection.
- GISNET public configuration discovery and ArcGIS object-ID pagination connector. When its service fails, OSM footprints are explicitly community-sourced discovery data.
- Public Complot parcel search and building-file tables. Sources and gaps persist in dossiers; permit history is never mislabeled as original construction evidence.
- Bounded document download, PDF text extraction and optional Hebrew/English OCR with page references. OCR never automatically verifies critical facts.
- Polygon validation in the official city boundary; building centroid selection in EPSG:2039, inclusive boundary; parcel overlap diagnostics.
- Versioned conservative policy checks with official PDF page references; unknowns block readiness; mandatory filters and lexicographic ranking.
- Background searches, persisted checkpoints, restart recovery, retry, immutable dossier snapshots, transactional entitlement and duplicate keys.
- PDF dossier and Excel input/formula exports, including clearly marked incomplete drafts. Scenario API refuses profit calculation without a supported planning basis.

## Actual findings and limits

See [source verification](docs/source-verification.md) and [field matrix](docs/field-matrix.md). The ten-building audit is in `data/verification/sample_audit.json`; all ten are discovery records requiring verification, not three saleable opportunities. The broader collection contained 185 footprints and 353 parcels.

The Shoshanim 4 experiment proves that a specific building can be populated when the archive documents are identified. The uploaded 1970 permit plan is byte-identical to the municipal archive copy. Building file 5848, current parcel 6529/167, six apartments, three residential floors over open pilotis, original areas, the 2013 alteration permit, and absence of a listed seismic-strengthening permit were captured with evidence. The building passes all six building-level threshold tests. A conservative preliminary policy calculation gives a 578.59 m² lawful above-ground base and a 2,314.36 m² 400% ceiling, with an indicative 17–19-unit range. This remains a draft dossier because the parcel's strategic-map classification and the effect of TAMA 70 have not been resolved into a supported detailed planning basis.

In the area-wide collector, municipal geometry queries failed and archive requests became rate limited. Existing apartment counts, legal areas, original permits and strengthening history therefore remain unknown for most buildings. The targeted Shoshanim 4 workflow works because it follows and preserves the exact archive records for one known building. Parcel-specific planning basis is still a delivery blocker. No market price or profit result has been invented.

The threshold rules are a partial screening implementation of the municipality's published policy, not a complete legal eligibility engine. Current collectors cannot produce a ready dossier from these sources alone. Parcel-pair geometry is tested but **pair delivery remains disabled** until public-separation evidence, parcel scope, building completeness, and combined planning/economic evidence are available. Planning lots are distinct from cadastral parcels and remain unknown when not identified.

This local pilot has one company, no authentication, no real payments and no enforceable commercial reservations. Bind to localhost. Package size is three; another simulated package can be opened only after exhaustion. Incomplete drafts never count as delivered.

## Verification

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -X utf8 scripts/verify_sample.py
```

The live audit performs public read-only queries and saves evidence; it may encounter source rate limits. Its requests are cached. `scripts/probe_sources.py` preserves source catalog responses. Optional OCR needs Tesseract plus `heb` and `eng` data (bundled in Docker); otherwise scanned pages explicitly report `ocr_unavailable`.

Pilot settings: `MAX_AREA_M2` (250000), `MAX_RADIUS_M` (250), `MAX_BUILDINGS` (500), `MAX_PARCELS` (1000), `ARCHIVE_INTERVAL_SECONDS` (10), `CACHE_SECONDS` (86400), `SOURCE_MAX_AGE_DAYS` (30), `SHAKED_DATA`. These are operational defaults, not approved commercial thresholds. The 30-day gate measures retrieval recency, not assurance of source currency; source dates are preserved separately.

API documentation: `/docs`. No API accepts arbitrary source URLs. User-controlled evidence and archive HTML are escaped in the interface. Original HTML is never executed. The server stores raw evidence under `data/cache` and extracted documents under `data/documents`.

## OpenAI extraction experiment

The first real API experiment is intentionally bounded to the scanned 1970 permit plan for Hashoshanim 4. Set `OPENAI_API_KEY` in the PowerShell session that runs the command, then run:

```powershell
.venv/Scripts/python.exe scripts/run_openai_hashoshanim_experiment.py --max-usd 1
```

For the free local OCR experiment, install Tesseract with Hebrew and English language data, then run:

```powershell
.venv/Scripts/python.exe scripts/run_local_hashoshanim_ocr.py
```

It saves the rendered source tiles and one raw Hebrew OCR text file per tile under
`data/experiments/hashoshanim-4-1970-plan-local-ocr`. It makes no network or API call.

### Zero-cost browser collection fallback

The normal collector prefers public structured endpoints. When a municipal document is
only reachable through a public browser flow, the bounded Playwright fallback uses the
installed Microsoft Edge browser and saves the PDF together with its public URLs, retrieval
time and SHA-256 hash. It does not bypass login, CAPTCHA or access controls.

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/collect_neve_israel_playwright.py
```

This collection stage has no API charge. Local Tesseract and human review remain the
zero-cost extraction route for scanned documents.

### Citywide building-file catalog

The resumable catalog discovers all public Herzliya building files street by street, checks
the declared result count, deduplicates file numbers, and then stores each file's metadata
and raw public HTML in the local database. Ten streets or files are processed by default:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/sync_herzliya_archive.py discover --limit 10
.venv/Scripts/python.exe -X utf8 scripts/sync_herzliya_archive.py hydrate --limit 10
.venv/Scripts/python.exe -X utf8 scripts/sync_herzliya_archive.py status
```

For a long resumable run, use `scripts/run_citywide_catalog.py`. Stop it at any time and run
it again; completed rows are not fetched again. A failed street prevents the status from
claiming full coverage. The canonical scope and evidence rules are in
[`docs/pipeline-decisions.md`](docs/pipeline-decisions.md).

The script renders overlapping tiles, asks the Responses API for strict JSON evidence, counts input tokens before the model call, and refuses to run above the configured ceiling. It saves the raw structured result, token usage and estimated cost under `data/experiments`, which is deliberately ignored by Git.
