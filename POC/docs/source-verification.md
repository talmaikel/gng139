# Source verification — 7 September 2026

## Evidence collected

The source probe preserves URLs, HTTP outcomes, retrieved bodies and timestamps in `data/verification`. A successful HTTP 200 was not sufficient: GIS `GetJson` initially returned an HTML error page. The public `minisite=public` request produced the actual layer catalog.

GovMap advertised seven WFS feature types, including cadastral parcels and municipal boundaries. Building and planning layers were not advertised. The verified Herzliya feature has `CR_LAMAS=6400`. The parcel schema contains GUSH_NUM, GUSH_SUFFI, PARCEL, LEGAL_AREA, SYS_DATE and geometry.

The municipal application's own GetMap response confirmed its internal ArcGIS service URL and public proxy. The proxy returned 500 after a normal public session; direct access closed the connection. Its national XPlan URL failed TLS negotiation from this Python environment. These failures do not establish that the sources are globally unavailable.

The official archive page publishes Complot scripts with site_id 121. Its building search script defines GetTikimByGush; the routes script defines GetTikFile. Following these public read-only requests returned real building files containing addresses, parcel references, plan tables and permit histories. Later requests received 429. Collection now spaces archive requests and stops additional archive queries in a job after a rate limit.

## Ten-building audit

The small-area collection returned 185 OSM building ways selected by centroid and 353 official parcels. Ten stable building IDs were checked. `sample_audit.json` contains the join fractions, exact source requests, returned building files and failures. Several footprints intersect more than one parcel; these are flagged, not forced into an arbitrary parcel. Some buildings share a parcel, and must never be counted as separate paid opportunities without planning-lot verification.

The sample proves **real geometry → official parcel → public archive** collection is possible. It does not establish apartment counts, complete permit evidence or automatic saleable readiness. No candidate has been delivered and the simulated entitlement remains three.

## Research corrections

- WFS access was verified, but the actual catalog does not support the research's broader implied building/planning coverage.
- The service/proxy architecture is confirmed by current public configuration; successful proxy querying is not confirmed.
- Reducing urllib3 does not change Python's linked OpenSSL version. No library downgrade or disabled TLS verification was used.
- A source's retrieval date and its underlying update date are separate evidence fields.
- The municipal PDF is hosted in an April 2026 path but identifies its update date as 17.02.2026. The rules reference the document's date and pages, not the upload-path month as the policy date.

## Next data gate

Ready delivery requires reliable original permit extraction, legal apartment/area counts, strengthening history, planning-lot mapping, checks for overriding plans, and approved financial assumptions. The POC shows those gaps rather than fabricating three opportunities. Public document automation and OCR are available, but critical values from unvalidated extraction are not automatically promoted to verified evidence.
