"""
Financial feasibility calculator ("Generic Report 0").

Pure Python, no Excel/COM runtime: projects total revenue and construction
expense for an urban-renewal project, splits new building area between
existing tenants (compensation) and the developer (sellable), and returns
the developer's profit margin.
"""

from app.services.economic.schemas import FeasibilityInput, FeasibilityResult


def calculate_feasibility(inputs: FeasibilityInput) -> FeasibilityResult:
    # Each existing unit is replaced 1:1 using its proportional share of the new
    # buildable area, plus any additional per-unit compensation sqm. Whatever
    # buildable area remains is sellable and belongs to the developer.
    average_unit_sqm = (inputs.buildable_area_sqm / inputs.existing_units) if inputs.existing_units > 0 else 0.0
    tenant_allocation_sqm = min(
        inputs.existing_units * (average_unit_sqm + inputs.tenant_compensation_sqm_per_existing_unit),
        inputs.buildable_area_sqm,
    )
    developer_allocation_sqm = inputs.buildable_area_sqm - tenant_allocation_sqm

    total_revenue_ils = developer_allocation_sqm * inputs.sale_price_per_sqm

    total_construction_cost_ils = inputs.buildable_area_sqm * inputs.construction_cost_per_sqm
    total_soft_cost_ils = total_construction_cost_ils * inputs.soft_cost_ratio
    total_demolition_cost_ils = inputs.existing_units * inputs.demolition_cost_per_unit

    total_cost_ils = total_construction_cost_ils + total_soft_cost_ils + total_demolition_cost_ils
    projected_profit_ils = total_revenue_ils - total_cost_ils
    profit_margin_ratio = (projected_profit_ils / total_revenue_ils) if total_revenue_ils else 0.0

    return FeasibilityResult(
        total_revenue_ils=round(total_revenue_ils, 2),
        total_construction_cost_ils=round(total_construction_cost_ils, 2),
        total_soft_cost_ils=round(total_soft_cost_ils, 2),
        total_demolition_cost_ils=round(total_demolition_cost_ils, 2),
        tenant_allocation_sqm=round(tenant_allocation_sqm, 2),
        developer_allocation_sqm=round(developer_allocation_sqm, 2),
        total_cost_ils=round(total_cost_ils, 2),
        projected_profit_ils=round(projected_profit_ils, 2),
        profit_margin_ratio=round(profit_margin_ratio, 4),
        meets_developer_target=profit_margin_ratio >= inputs.developer_profit_target_ratio,
    )
