from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.services.economic.schemas import FeasibilityInput


class UnitTypeOption(BaseModel):
    """A developer-sale apartment type already priced by market-data.

    B15 intentionally receives these values from the existing valuation
    pipeline. It does not invent apartment sizes or fetch another price feed.
    """

    key: str = Field(min_length=1)
    rooms: float = Field(gt=0, le=10)
    area_sqm: float = Field(gt=0)
    price_per_sqm_ils: float = Field(gt=0)


class HerzliyaMixPolicy(BaseModel):
    """Only numeric constraints stated by Herzliya's 17.02.2026 policy.

    The policy also says typical floors should contain mainly 3- and 4-room
    apartments. Because it gives no numeric threshold for "mainly", B15 does
    not silently turn that wording into a made-up percentage. The caller may
    choose only 3/4/5-room options for the beta, and the result carries an
    explicit warning that architectural review is still required.
    """

    min_unit_multiplier: float = Field(default=2.8, gt=0)
    max_unit_multiplier: float = Field(default=3.18, gt=0)
    small_unit_min_sqm: float = Field(default=56.0, gt=0)
    small_unit_max_sqm: float = Field(default=80.0, gt=0)
    min_small_unit_share: float = Field(default=0.25, ge=0, le=1)
    micro_unit_max_sqm: float = Field(default=55.0, gt=0)
    max_micro_unit_share: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.max_unit_multiplier < self.min_unit_multiplier:
            raise ValueError("max_unit_multiplier must be >= min_unit_multiplier")
        if self.small_unit_max_sqm < self.small_unit_min_sqm:
            raise ValueError("small_unit_max_sqm must be >= small_unit_min_sqm")
        if self.micro_unit_max_sqm >= self.small_unit_min_sqm:
            raise ValueError("micro range must end below the small-unit range")
        return self


class UnitMixOptimizationInput(BaseModel):
    """Inputs B15 consumes from data that already exists in Shaked Engine."""

    # B3/B6 output. Per-household compensation is deliberately blocked when
    # only an average exists; the existing dwelling-unit service makes the
    # same distinction.
    existing_unit_areas_sqm: list[float] = Field(min_length=1)

    # Existing rights/economic input. This is total above-ground permitted
    # area; main_area_ratio converts it to saleable/main apartment area in the
    # same way as the Generic Report 0 calculator.
    buildable_area_sqm: float = Field(gt=0)
    main_area_ratio: float = Field(gt=0, le=1)

    # The already-resolved Generic Report 0 input (construction costs,
    # financing, tenant costs, levy input, VAT, target margin, etc.). B15
    # overrides only the fields that the chosen mix actually changes.
    economic_input: FeasibilityInput
    economic_missing_inputs: list[str] = Field(default_factory=list)

    # User choice. If omitted, a labelled market-default value must be passed
    # by the caller/assumptions layer. There is intentionally no magic B15
    # default in this module.
    compensation_sqm_per_existing_unit: float | None = Field(default=None, ge=0)
    default_compensation_sqm_per_existing_unit: float = Field(ge=0)
    default_compensation_label: str = Field(default="market_default", min_length=1)

    # B16 market-data output transformed into concrete candidate apartment
    # types. B15 never fetches prices itself.
    unit_types: list[UnitTypeOption] = Field(min_length=1)
    policy: HerzliyaMixPolicy = Field(default_factory=HerzliyaMixPolicy)
    max_results: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_consistency(self):
        keys = [item.key for item in self.unit_types]
        if len(keys) != len(set(keys)):
            raise ValueError("unit type keys must be unique")
        if self.economic_input.existing_units != len(self.existing_unit_areas_sqm):
            raise ValueError("economic_input.existing_units must match the per-apartment schedule")
        if abs(self.economic_input.buildable_area_sqm - self.buildable_area_sqm) > 1e-6:
            raise ValueError("economic_input.buildable_area_sqm must match B15 buildable_area_sqm")
        if abs(self.economic_input.main_area_ratio - self.main_area_ratio) > 1e-9:
            raise ValueError("economic_input.main_area_ratio must match B15 main_area_ratio")
        return self


class UnitMixCandidate(BaseModel):
    counts: dict[str, int]
    total_new_units: int
    developer_units: int
    tenant_units: int
    tenant_allocation_sqm: float
    developer_used_sqm: float
    developer_available_sqm: float
    unused_developer_sqm: float
    small_units: int
    micro_units: int
    small_unit_share: float
    micro_unit_share: float
    gross_developer_revenue_ils: float
    blended_sale_price_per_sqm_ils: float

    # Exact candidate revenue is passed through Generic Report 0, so ranking
    # uses the same project costs/finance/tenant/levy model as the dossier.
    developer_revenue_ils: float
    total_cost_ils: float
    projected_profit_ils: float
    profit_margin_on_cost_ratio: float
    meets_developer_target: bool
    economics_deliverable: bool


class UnitMixOptimizationResult(BaseModel):
    compensation_sqm_per_existing_unit: float
    compensation_source: str
    tenant_allocation_sqm: float
    total_main_area_sqm: float
    developer_available_sqm: float
    feasible: bool
    candidates: list[UnitMixCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
