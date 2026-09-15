# Shakdan · Shaked Alternative screening for Herzliya

Shakdan finds and packages urban-renewal opportunities under Israel's **Shaked Alternative**
(Planning and Building Law, Amendment 139, §70A–§70B: demolish and rebuild at up to 400% of
the existing built area), starting with the city of Herzliya.

A developer draws an area on the map, sets conditions and preferences, and receives up to
three **opportunity dossiers**: the §70A threshold chain with a cited source for every gate,
evidence with provenance for every field, a feasibility scenario ("Report 0"), the betterment
levy ceiling and estimate, and the gaps that remain open. Dossiers export to PDF and to an
Excel workbook with live formulas.

The product itself is in Hebrew. Code, commits, pull requests and repository documentation
are in English; task tracking in GitHub issues may stay in Hebrew.

## Repository layout

| Path | What it is |
|---|---|
| [`apps/shaked-engine/`](apps/shaked-engine/) | **The product.** FastAPI backend, Next.js frontend, PostgreSQL + PostGIS. All development happens here. |
| [`POC/`](POC/) | The earlier proof of concept. Reference only — but the engine still seeds parcels from `POC/layer_a/data` and reads the city boundary from it, so do not move or delete it without the migration planned in issue #42. |
| [`packages/`](packages/) | Shared packages. |

## Where to start

- **Run it locally:** [`apps/shaked-engine/README.md`](apps/shaked-engine/README.md)
- **How to contribute:** [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **What exists and what is next:** [`apps/shaked-engine/PRODUCT_STRUCTURE.md`](apps/shaked-engine/PRODUCT_STRUCTURE.md)
- **The demo script (Hebrew):** [`apps/shaked-engine/DEMO.md`](apps/shaked-engine/DEMO.md)
- **Work plan and task tracking:** [issue #6](https://github.com/talmaikel/gng139/issues/6)

## Two documents you must not bypass

- **[`POC/layer_a/data/DATA_LAW.md`](POC/layer_a/data/DATA_LAW.md)** — what may be collected
  and stored. Facts may be stored freely; permit drawings are deleted after extraction;
  applicant names are never read; and **the municipal archive is never swept** — building
  files are fetched one at a time, on a customer's request, at a slow shared pace.
- **[`POC/layer_a/data/DOCUMENTS.md`](POC/layer_a/data/DOCUMENTS.md)** — the register of the
  policy documents that decide eligibility, including a warning about a procedure that is
  still published on the municipal site but is no longer in force.

## Tel Aviv-Yafo

A possible future extension, not in scope. What was learned is in
[`POC/data/cities/tel-aviv/README.md`](POC/data/cities/tel-aviv/README.md) and
[`apps/shaked-engine/backend/app/cities/tel_aviv/README.md`](apps/shaked-engine/backend/app/cities/tel_aviv/README.md).
