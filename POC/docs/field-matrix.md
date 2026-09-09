# Dossier field coverage

| Required field | Source / join | Verification and gap |
|---|---|---|
| City boundary | GovMap `muni_il`, `CR_LAMAS=6400` | Verified one feature named הרצליה; EPSG:2039 |
| Building footprint | Municipal ArcGIS preferred; OSM way fallback | Municipal query failed. Community geometry never establishes official readiness |
| Block / parcel / suffix | GovMap `Parcels_ITM`: GUSH_NUM, PARCEL, GUSH_SUFFI | Verified. Stable commercial keys use all three, not address or transient feature ID |
| Building–parcel link | Spatial footprint overlap in ITM | Derived; multiple intersections flagged. Not proof of planning-lot identity |
| Cadastral area | LEGAL_AREA, otherwise polygon-derived area | Verified schema. Derived area distinctly labeled |
| Planning lot | Archive lot/plan tables or planning GIS | Distinct entity, presently unverified; never replaced with parcel ID |
| Address / file number | Complot GetTikimByGush → GetTikFile | Real records retrieved; exact address label used with evidence |
| Existing apartments / floors | Original permit, approved legal building state | Missing. OSM tags and permit list dates do not suffice |
| Original permit date | Original construction permit | Missing. Later alteration permit dates not substituted |
| Legal residential share | Approved use and area schedule | Missing |
| Strengthening / engineer opinion | Permits and engineer evidence | Missing; no-record-found is not proof of no strengthening |
| Applicable plans | Archive tables; XPlan spatial layer | Archive references available; XPlan TLS failure; completeness unverified |
| Threshold rules | Municipal Shaked policy, updated 17.02.2026, pages 2–3 | Source retrieved. Partial conservative screening implemented |
| Planning scenario basis | Verified legal areas and applicable planning limits | Missing; no automatic ×4 rights assumption |
| Commercial costs / prices | Explicit approved pilot assumption library | Not approved; no invented defaults; calculation gated |
| Documents / page evidence | Public PDFs; native text / optional OCR | General policy PDF retrieved; parcel-specific permit evidence incomplete |
| Source freshness | Retrieved timestamp plus source SYS_DATE / reported date | Both retained; retrieval date does not establish currency |

Certainty classes: official, derived, manually_verified, community, missing, conflict. Community is an additional conservative discovery category. Conflicting observations must retain individual evidence; no last-writer-wins resolution is permitted for critical fields.
