from pydantic import BaseModel, Field


class FeasibilityInput(BaseModel):
    """Inputs to the 'Generic Report 0' financial feasibility calculator."""

    plot_area_sqm: float = Field(gt=0)
    existing_units: int = Field(ge=0)
    buildable_area_sqm: float = Field(gt=0, description="Total permitted above-ground building area (sqm)")

    sale_price_per_sqm: float = Field(gt=0, description="Expected sale price per sqm of new construction (ILS)")
    construction_cost_per_sqm: float = Field(gt=0, description="Hard construction cost per sqm (ILS)")

    soft_cost_ratio: float = Field(default=0.15, ge=0, description="Soft costs (planning/permits/financing) as a ratio of construction cost")
    demolition_cost_per_unit: float = Field(default=150_000, ge=0)

    tenant_compensation_sqm_per_existing_unit: float = Field(
        default=0.0, ge=0, description="Extra sqm of new apartment granted to each existing tenant, beyond a 1:1 replacement"
    )
    developer_profit_target_ratio: float = Field(default=0.20, ge=0, description="Developer's minimum required profit margin")


class FeasibilityResult(BaseModel):
    """Output of the feasibility calculator, as pure JSON — no Excel runtime involved."""

    total_revenue_ils: float
    total_construction_cost_ils: float
    total_soft_cost_ils: float
    total_demolition_cost_ils: float
    tenant_allocation_sqm: float
    developer_allocation_sqm: float
    total_cost_ils: float
    projected_profit_ils: float
    profit_margin_ratio: float
    meets_developer_target: bool
