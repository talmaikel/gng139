# B15 — planned unit mix

B15 supplies the explicit `planned_unit_mix` that the market-data service needs before it may calculate a project-wide transaction-based price.

## Product decision

The mix is **not** a fixed city-wide ratio and is **not** silently inferred from one average apartment. It is generated per opportunity by optimizing projected developer profit under the numeric Herzliya policy constraints and the compensation offer to the existing owners.

Inputs are reused from existing Shaked Engine stages:

- Existing apartment areas: the B3 dwelling-unit schedule. Per-household compensation runs only when the schedule is complete and human verified.
- Buildable area and unit-count constraints: the existing Herzliya rights assessment.
- Room-level prices and comparable counts: the latest stored B1/B16 comparable-sales valuation. B15 performs no scraping.
- Project costs and profit target: the existing versioned Generic Report 0 assumptions and B2 construction-cost resolver.
- Owner compensation: the developer-supplied extra sqm per existing apartment. If omitted, the versioned Herzliya assumption is used (`25 sqm`, status `ESTIMATE`, source `תוספת מקובלת בהתחדשות עירונית`).

## What is data and what is an estimate

The optimization result is stored with `status=estimate`. The three beta target apartment areas — 75 sqm for 3 rooms, 100 sqm for 4 rooms and 125 sqm for 5 rooms — are explicit modelling assumptions. Herzliya policy defines the 56–80 sqm small-unit band but does not prescribe canonical 3/4/5-room areas. The assumption and its source text are persisted in `planned_unit_mix_meta`; they are not presented as municipal policy.

The market prices themselves are derived from the stored comparable transactions by the existing valuation engine. For each candidate mix, the existing Generic Report 0 calculator scores the exact enumerated developer-sale revenue and returns projected profit and profit-on-cost.

## Persisted shape

The recommended mix is written to `Opportunity.metadata_json` in the format already consumed by the market-data pipeline:

```json
{
  "planned_unit_mix": [
    {"rooms": 3, "area_sqm": 75, "units": 8},
    {"rooms": 4, "area_sqm": 100, "units": 6}
  ],
  "planned_unit_mix_meta": {
    "source": "b15_profit_optimizer",
    "status": "estimate",
    "objective": "maximize_projected_developer_profit_ils"
  }
}
```

After persistence B15 creates a new immutable market-valuation snapshot from the **already stored** comparable sales and the selected mix. It makes `is_unit_mix_adjusted=true`, so the dossier can use the transaction-based blended price immediately without a network request.

## Recalculation

`POST /api/v1/unit-mix/{opportunity_id}/optimize` accepts an optional `compensation_sqm_per_existing_unit`. Calling it again with a different value recalculates owner allocation, available developer area, feasible mixes and Report-0 profit. Omitting the field uses the labelled default above.

W8: `persist` defaults to false and is refused (403) for non-staff users. The opportunity row is shared by every company it is delivered to, so a saved mix leaked from one customer's dossier to another's; the dossier no longer reads `planned_unit_mix`. Customers compute a mix in the dossier's scenario calculator (`POST /api/v1/candidates/{city}/{id}/dossier/scenario` with `mix: "optimize"` or 3/4/5-room counts), where the mix drives developer revenue and nothing is stored.

## Herzliya constraints implemented

The optimizer enforces the policy's numeric constraints: total unit multiplier 2.8–3.18, at least 25% small units in the 56–80 sqm band, and no more than 10% micro units up to 55 sqm. The policy also says typical floors should contain mainly 3- and 4-room apartments, but does not define a numeric threshold; B15 therefore does not invent one and keeps an architectural-review warning. The 10% accessibility requirement is treated as a design requirement rather than a separate size bucket.
