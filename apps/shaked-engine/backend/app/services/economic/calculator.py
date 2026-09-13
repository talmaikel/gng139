"""
Financial feasibility calculator ("Generic Report 0" -- Shaked PRD section 6.4).

Pure Python, no Excel/COM runtime: projects revenue and expense for an
urban-renewal project, splits the new building between existing tenants
(compensation) and the developer (sellable), and returns the profit margin
on cost (PRD requirement ECO-01).

Per the PRD, this tool explicitly is NOT a signed appraiser's report, does
not determine final rights or approved feasibility, and must never present
an estimated figure as a verified one -- callers (see app/worker.py) are
responsible for only invoking this with a substantiated buildable area, and
for surfacing which inputs are data vs. estimate vs. missing.

**Three corrections, 13.09.2026, after the first version returned 305%
profit on cost for a typical candidate:**

1. *Service area was sold at apartment prices.* The 400% cap of §70ב(א)(1)
   explicitly includes service areas and safe rooms. They are built and they
   are not sold at 45,000 ILS/sqm. Revenue now comes off main area only.

2. *The land was not in the cost base.* The apartments handed to existing
   tenants ARE the consideration for the land -- roughly 30M ILS on a
   typical candidate. Netting them out of revenue while leaving them out of
   cost put the project's largest single input outside the denominator, and
   "profit on cost" stopped meaning anything.

3. *Whole cost lines were absent.* Finance, marketing, guarantees, the
   tenants' rent for three and a half years, their lawyer, and the
   underground parking that the cap does not count but the developer still
   pays for.

What remains unresolved is the betterment levy: whether amendment 139
carries an exemption is a question for counsel, and it is large enough to
decide a project on its own. It enters as a ratio that defaults to zero and
is marked MISSING in the assumptions library, so a scenario that ignores it
cannot be reported as deliverable.
"""

from app.services.economic.schemas import FeasibilityInput, FeasibilityResult


def calculate_feasibility(inputs: FeasibilityInput,
                          missing_inputs: list[str] | None = None) -> FeasibilityResult:
    """Run the scenario.

    `missing_inputs` names the commercial inputs that are genuinely unknown
    (see `EconomicAssumptionSet.blocking`). The numbers are still computed --
    a scenario built on a placeholder is useful to reason with -- but the
    result carries `is_deliverable=False`, so it cannot be handed to a client
    as though it rested on data.
    """
    # ── שטחים ──
    sellable_main_sqm = inputs.buildable_area_sqm * inputs.main_area_ratio
    underground_sqm = inputs.buildable_area_sqm * inputs.underground_ratio
    constructed_area_sqm = inputs.buildable_area_sqm + underground_sqm

    tenant_requirement_sqm = inputs.existing_units * (
        inputs.average_existing_unit_sqm + inputs.tenant_compensation_sqm_per_existing_unit
    )
    tenants_fit = tenant_requirement_sqm <= sellable_main_sqm
    tenant_allocation_sqm = min(tenant_requirement_sqm, sellable_main_sqm)
    developer_allocation_sqm = sellable_main_sqm - tenant_allocation_sqm

    # ── הכנסות, נטו ממע״מ ──
    # מחיר שוק מצוטט כולל מע״מ ועלויות מוצגות נטו. בלי היישור הזה המרווח
    # מנופח בשיעור המע״מ עוד לפני שורת עלות אחת חסרה.
    net_price = (inputs.sale_price_per_sqm / (1 + inputs.vat_rate)
                 if inputs.sale_price_includes_vat else inputs.sale_price_per_sqm)
    total_revenue_ils = sellable_main_sqm * net_price
    land_cost_ils = tenant_allocation_sqm * net_price
    developer_revenue_ils = total_revenue_ils - land_cost_ils

    # ── עלויות ──
    total_construction_cost_ils = inputs.buildable_area_sqm * inputs.construction_cost_per_sqm
    total_underground_cost_ils = underground_sqm * inputs.underground_cost_per_sqm
    total_soft_cost_ils = (total_construction_cost_ils + total_underground_cost_ils) * inputs.soft_cost_ratio
    total_demolition_cost_ils = inputs.existing_units * inputs.demolition_cost_per_unit
    total_tenant_cost_ils = inputs.existing_units * (
        inputs.tenant_rent_months * inputs.tenant_monthly_rent_ils
        + inputs.tenant_moving_cost_ils
        + inputs.tenant_legal_cost_per_unit_ils
    )
    total_marketing_ils = total_revenue_ils * inputs.marketing_ratio
    total_guarantees_ils = total_revenue_ils * inputs.guarantees_ratio
    betterment_levy_ils = total_revenue_ils * inputs.betterment_levy_ratio

    # מימון נגזר מכל השאר, ולכן הוא מחושב אחרון ואינו נכנס לבסיס של עצמו.
    cost_before_finance = (land_cost_ils + total_construction_cost_ils
                           + total_underground_cost_ils + total_soft_cost_ils
                           + total_demolition_cost_ils + total_tenant_cost_ils
                           + total_marketing_ils + total_guarantees_ils
                           + betterment_levy_ils)
    total_finance_ils = cost_before_finance * inputs.finance_ratio
    total_cost_ils = cost_before_finance + total_finance_ils

    projected_profit_ils = total_revenue_ils - total_cost_ils
    profit_margin_on_cost_ratio = (projected_profit_ils / total_cost_ils) if total_cost_ils > 0 else 0.0

    r = round
    return FeasibilityResult(
        sellable_main_sqm=r(sellable_main_sqm, 2),
        tenant_allocation_sqm=r(tenant_allocation_sqm, 2),
        developer_allocation_sqm=r(developer_allocation_sqm, 2),
        constructed_area_sqm=r(constructed_area_sqm, 2),
        total_revenue_ils=r(total_revenue_ils, 2),
        developer_revenue_ils=r(developer_revenue_ils, 2),
        land_cost_ils=r(land_cost_ils, 2),
        total_construction_cost_ils=r(total_construction_cost_ils, 2),
        total_underground_cost_ils=r(total_underground_cost_ils, 2),
        total_soft_cost_ils=r(total_soft_cost_ils, 2),
        total_demolition_cost_ils=r(total_demolition_cost_ils, 2),
        total_tenant_cost_ils=r(total_tenant_cost_ils, 2),
        total_marketing_ils=r(total_marketing_ils, 2),
        total_guarantees_ils=r(total_guarantees_ils, 2),
        total_finance_ils=r(total_finance_ils, 2),
        betterment_levy_ils=r(betterment_levy_ils, 2),
        total_cost_ils=r(total_cost_ils, 2),
        projected_profit_ils=r(projected_profit_ils, 2),
        profit_margin_on_cost_ratio=r(profit_margin_on_cost_ratio, 4),
        meets_developer_target=profit_margin_on_cost_ratio >= inputs.developer_profit_target_ratio,
        tenants_fit=tenants_fit,
        inputs_missing=sorted(missing_inputs or []),
        is_deliverable=not missing_inputs,
    )
