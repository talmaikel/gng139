"""
Financial feasibility calculator ("Generic Report 0" -- Shaked PRD section 6.4).

Pure Python, no Excel/COM runtime: projects total revenue and construction
expense for an urban-renewal project, splits new building area between
existing tenants (compensation) and the developer (sellable), and returns
the profit margin on cost (PRD requirement ECO-01).

Per the PRD, this tool explicitly is NOT a signed appraiser's report, does
not determine final rights or approved feasibility, and must never present
an estimated figure as a verified one -- callers (see app/worker.py) are
responsible for only invoking this with a substantiated buildable area, and
for surfacing which inputs are data vs. estimate vs. missing.
"""

from app.services.economic.schemas import FeasibilityInput, FeasibilityResult


def calculate_feasibility(inputs: FeasibilityInput) -> FeasibilityResult:
    # Each existing unit is replaced 1:1 at its (assumed) EXISTING size, plus
    # any additional per-unit compensation sqm -- NOT a share of the new
    # buildable area. Sizing the replacement off the new building instead of
    # the old one would always consume exactly 100% of buildable_area_sqm by
    # construction (existing_units * (buildable_area_sqm / existing_units) ==
    # buildable_area_sqm, identically, regardless of building size), leaving
    # the developer with zero allocation no matter how much is built -- a
    # real bug found via testing, not a simplification.
    tenant_allocation_sqm = min(
        inputs.existing_units * (inputs.average_existing_unit_sqm + inputs.tenant_compensation_sqm_per_existing_unit),
        inputs.buildable_area_sqm,
    )
    developer_allocation_sqm = inputs.buildable_area_sqm - tenant_allocation_sqm

    total_revenue_ils = developer_allocation_sqm * inputs.sale_price_per_sqm

    total_construction_cost_ils = inputs.buildable_area_sqm * inputs.construction_cost_per_sqm
    total_soft_cost_ils = total_construction_cost_ils * inputs.soft_cost_ratio
    total_demolition_cost_ils = inputs.existing_units * inputs.demolition_cost_per_unit

    total_cost_ils = total_construction_cost_ils + total_soft_cost_ils + total_demolition_cost_ils
    projected_profit_ils = total_revenue_ils - total_cost_ils
    # Per the Shaked PRD (6.4, requirement ECO-01): "profit rate is the
    # difference divided by expenses, and only when the denominator is
    # positive" -- profit-on-COST, not on revenue.
    profit_margin_on_cost_ratio = (projected_profit_ils / total_cost_ils) if total_cost_ils > 0 else 0.0

    return FeasibilityResult(
        total_revenue_ils=round(total_revenue_ils, 2),
        total_construction_cost_ils=round(total_construction_cost_ils, 2),
        total_soft_cost_ils=round(total_soft_cost_ils, 2),
        total_demolition_cost_ils=round(total_demolition_cost_ils, 2),
        tenant_allocation_sqm=round(tenant_allocation_sqm, 2),
        developer_allocation_sqm=round(developer_allocation_sqm, 2),
        total_cost_ils=round(total_cost_ils, 2),
        projected_profit_ils=round(projected_profit_ils, 2),
        profit_margin_on_cost_ratio=round(profit_margin_on_cost_ratio, 4),
        meets_developer_target=profit_margin_on_cost_ratio >= inputs.developer_profit_target_ratio,
    )
