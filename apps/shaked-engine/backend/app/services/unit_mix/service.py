from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.herzliya import new_build_prices
from app.models.opportunity import Opportunity
from app.services.dwelling_units import load_units, resolve_existing_unit_area
from app.services.economic.assumptions import get_assumptions
from app.services.economic.construction_costs import (
    resolve_construction_cost_per_sqm,
    resolve_underground_cost_per_sqm,
)
from app.services.economic.schemas import FeasibilityInput
from app.services.evidence_store import fields_for
from app.services.unit_mix.optimizer import optimize_unit_mix
from app.services.unit_mix.schemas import (
    UnitMixOptimizationInput,
    UnitMixOptimizationResult,
    UnitTypeOption,
)


# B15 beta apartment-size assumptions. Herzliya policy specifies the 56-80 sqm
# small-unit band, but does not prescribe one canonical area for 3/4/5-room
# apartments. These sizes are therefore explicit ESTIMATES, not city policy.
# They are kept in one place and persisted in planned_unit_mix_meta so a later
# market/architectural source can replace them without changing the optimizer.
DEFAULT_UNIT_AREAS_SQM: dict[int, float] = {3: 75.0, 4: 100.0, 5: 125.0}
UNIT_AREA_ASSUMPTION_SOURCE = (
    "B15 beta modelling assumption: 3r=75 sqm, 4r=100 sqm, 5r=125 sqm; "
    "Herzliya policy defines only the 56-80 sqm small-unit band"
)


class UnitMixUnavailable(ValueError):
    """B15 cannot produce an auditable mix from the data currently available."""


@dataclass
class PreparedUnitMix:
    result: UnitMixOptimizationResult
    planned_unit_mix: list[dict[str, Any]]
    metadata: dict[str, Any]


def _assessment(opportunity: Opportunity) -> dict[str, Any]:
    return (opportunity.metadata_json or {}).get("assessment") or {}


def _economic_input(
    opportunity: Opportunity,
    *,
    buildable_area_sqm: float,
    average_existing_unit_sqm: float,
    compensation_sqm: float,
) -> tuple[FeasibilityInput, list[str], str]:
    """Build the same versioned Report-0 input family used by the dossier.

    B15 deliberately does not create a second cost model. Construction and
    underground costs resolve through the existing B2 services; all remaining
    rates come from the versioned city assumptions library.
    """

    a = get_assumptions(opportunity.city_code)
    assessment = _assessment(opportunity)
    # The stored screening assessment keeps floors flat (`floors_low`); the
    # live one nests them. Reading only the nested form left floors=None, so
    # construction cost averaged every height band (7,367 vs the dossier's
    # 7,200) and the mix screen's margin sat a point below the dossier's.
    floors = ((assessment.get("floors") or {}).get("low")
              or assessment.get("floors_low"))
    construction = resolve_construction_cost_per_sqm(
        opportunity.city_code, developer_value=None, floors=floors
    )
    underground = resolve_underground_cost_per_sqm(opportunity.city_code)

    blocking = [
        key
        for key in a.blocking()
        if key not in {
            "average_existing_unit_sqm",  # resolved below: confirmed schedule, else building average
            "betterment_base_ils",        # dossier product decision: expose threshold instead
            "construction_cost_per_sqm_ils",
        }
    ]
    if construction.value_ils_per_sqm is None:
        blocking.append("construction_cost_per_sqm_ils")
        construction_cost = a.construction_cost_per_sqm_ils.value
    else:
        construction_cost = construction.value_ils_per_sqm

    underground_cost = (
        underground.value_ils_per_sqm or a.underground_cost_per_sqm_ils.value
    )
    # The optimizer overwrites this with each candidate's revenue per used sqm,
    # which is this same price while every size sells at it (_unit_types).
    # P1: the dossier's price for this block, so both screens stay on one price.
    sale_price, _ = new_build_prices.sale_price(opportunity.block, a.sale_price_per_sqm_ils.value)

    return (
        FeasibilityInput(
            plot_area_sqm=opportunity.area_sqm,
            existing_units=opportunity.existing_units,
            buildable_area_sqm=buildable_area_sqm,
            sale_price_per_sqm=sale_price,
            construction_cost_per_sqm=construction_cost,
            soft_cost_ratio=a.soft_cost_ratio.value,
            demolition_cost_ils=a.demolition_cost_ils.value,
            balcony_sqm_per_new_unit=a.balcony_sqm_per_new_unit.value,
            balcony_price_factor=a.balcony_price_factor.value,
            balcony_cost_per_sqm=a.balcony_cost_per_sqm_ils.value,
            average_new_unit_sqm=a.average_new_unit_sqm.value,
            tenants_supervisor_ils=a.tenants_supervisor_ils.value,
            consultants_per_new_unit_ils=a.consultants_per_new_unit_ils.value,
            plan_cost_ils=a.plan_cost_ils.value,
            permit_fee_per_sqm=a.permit_fee_per_sqm_ils.value,
            purchase_tax_ratio=a.purchase_tax_ratio.value,
            rights_value_per_sqm_ils=a.rights_value_per_sqm_ils.value,
            bank_fees_ratio=a.bank_fees_ratio.value,
            developer_profit_target_ratio=a.developer_profit_target_ratio.value,
            average_existing_unit_sqm=average_existing_unit_sqm,
            tenant_compensation_sqm_per_existing_unit=compensation_sqm,
            main_area_ratio=a.main_area_ratio.value,
            underground_ratio=a.underground_ratio.value,
            underground_cost_per_sqm=underground_cost,
            tenant_rent_months=a.tenant_rent_months.value,
            tenant_monthly_rent_ils=a.tenant_monthly_rent_ils.value,
            tenant_moving_cost_ils=a.tenant_moving_cost_ils.value,
            tenant_legal_cost_per_unit_ils=a.tenant_legal_cost_per_unit_ils.value,
            marketing_ratio=a.marketing_ratio.value,
            guarantees_ratio=a.guarantees_ratio.value,
            finance_ratio=a.finance_ratio.value,
            betterment_levy_rate=a.betterment_levy_rate.value,
            betterment_base_ils=a.betterment_base_ils.value,
            vat_rate=a.vat_rate.value,
        ),
        sorted(set(blocking)),
        a.version,
    )


def _unit_types(sale_price_per_sqm_ils: float) -> list[UnitTypeOption]:
    """The beta apartment sizes, all priced at the dossier's sale price.

    15.09 (Boaz): the comparables near the parcels are second-hand deals, and
    a second-hand price is not the sale price of a new building (B12). Pricing
    each room count from them put the mix screen at -17.6% while the dossier
    said +20.8% for the same parcel. Until a new-build price per room count
    exists, every size sells at the same per-sqm price the dossier uses, so the
    mix is chosen by area and Herzliya's constraints, and both screens rest on
    one price.
    """
    return [
        UnitTypeOption(
            key=f"{rooms}r",
            rooms=rooms,
            area_sqm=area,
            price_per_sqm_ils=sale_price_per_sqm_ils,
        )
        for rooms, area in DEFAULT_UNIT_AREAS_SQM.items()
    ]


def _numeric(field: dict[str, Any] | None) -> float | None:
    try:
        return float((field or {}).get("value"))
    except (TypeError, ValueError):
        return None


async def prepare_unit_mix(
    session: AsyncSession,
    opportunity: Opportunity,
    *,
    compensation_sqm_per_existing_unit: float | None,
    persist: bool = True,
) -> PreparedUnitMix:
    """Run B15 from the opportunity's existing B3/B16/Report-0 inputs.

    If ``persist`` is true, the recommended mix is written to
    ``opportunity.metadata_json['planned_unit_mix']``. The dossier shows it,
    and its profit does not move: no valuation snapshot is created, because a
    mix-weighted price of second-hand comparables must not become the sale
    price (see ``_unit_types``).
    """

    if opportunity.city_code != "herzliya":
        raise UnitMixUnavailable("B15 beta currently supports Herzliya only.")
    if not opportunity.existing_units or not opportunity.area_sqm:
        raise UnitMixUnavailable("חסרים מספר דירות קיים או שטח מגרש.")

    assessment = _assessment(opportunity)
    # W2: the same area the dossier runs on -- the policy-allowed area, and the
    # 400% cap only where no policy area could be computed.
    buildable = assessment.get("policy_area_sqm") or assessment.get("cap_400_sqm")
    if not buildable or buildable <= 0:
        raise UnitMixUnavailable("אין תקרת זכויות מבוססת לחלקה.")

    units = await load_units(session, opportunity.id)
    resolution = resolve_existing_unit_area(
        units,
        municipal_unit_count=opportunity.existing_units,
        existing_area_sqm=None,
    )
    assumptions = get_assumptions(opportunity.city_code)
    if resolution.per_unit_detail_available:
        verified_units = [
            unit for unit in units
            if not unit.requires_human_review and unit.area_sqm is not None
        ]
        existing_areas = [float(unit.area_sqm) for unit in verified_units]
        if len(existing_areas) != opportunity.existing_units:
            raise UnitMixUnavailable("לוח הדירות המאומת אינו מכסה את כל הדירות הקיימות.")
        existing_units_basis = "confirmed_schedule"
    else:
        # 15.09 (Boaz): no parcel has a confirmed schedule yet (0 of 699), so
        # requiring one meant the screen never produced a mix. The total owner
        # area is the same either way -- n x (average + c) equals the sum of
        # (area_i + c) -- so developer area and profit do not depend on it.
        # What the average blurs is how many owner apartments fall in the
        # 56-80 sqm band. It is the same average the dossier shows, from the
        # same resolution, and is persisted as the basis.
        fields = await fields_for(session, opportunity.id)
        resolution = resolve_existing_unit_area(
            units,
            municipal_unit_count=opportunity.existing_units,
            existing_area_sqm=_numeric(fields.get("existing_area")),
        )
        average = (resolution.average_existing_unit_sqm
                   or assumptions.average_existing_unit_sqm.value)
        if not average:
            raise UnitMixUnavailable("אין שטח דירה קיימת, גם לא ממוצע לבניין.")
        existing_areas = [float(average)] * opportunity.existing_units
        existing_units_basis = "building_average"
    default_comp = assumptions.tenant_compensation_sqm_per_existing_unit.value
    compensation = (
        compensation_sqm_per_existing_unit
        if compensation_sqm_per_existing_unit is not None
        else default_comp
    )

    sale_price, block_label = new_build_prices.sale_price(
        opportunity.block, assumptions.sale_price_per_sqm_ils.value)
    options = _unit_types(sale_price)

    average_existing = sum(existing_areas) / len(existing_areas)
    economic_input, missing, assumptions_version = _economic_input(
        opportunity,
        buildable_area_sqm=float(buildable),
        average_existing_unit_sqm=average_existing,
        compensation_sqm=compensation,
    )

    optimization = optimize_unit_mix(
        UnitMixOptimizationInput(
            existing_unit_areas_sqm=existing_areas,
            buildable_area_sqm=float(buildable),
            main_area_ratio=economic_input.main_area_ratio,
            economic_input=economic_input,
            economic_missing_inputs=missing,
            compensation_sqm_per_existing_unit=compensation_sqm_per_existing_unit,
            default_compensation_sqm_per_existing_unit=default_comp,
            default_compensation_label=(
                f"market_default:{assumptions.tenant_compensation_sqm_per_existing_unit.source}"
            ),
            unit_types=options,
        )
    )
    if not optimization.feasible or not optimization.candidates:
        raise UnitMixUnavailable(
            "לא נמצא תמהיל שעומד יחד בשטח הזמין ובאילוצי מדיניות הרצליה."
        )

    best = optimization.candidates[0]
    option_by_key = {option.key: option for option in options}
    planned_mix = [
        {
            "rooms": option_by_key[key].rooms,
            "area_sqm": option_by_key[key].area_sqm,
            "units": count,
        }
        for key, count in best.counts.items()
        if count > 0
    ]

    generated_at = datetime.now(timezone.utc)
    metadata = {
        "source": "b15_profit_optimizer",
        "status": "estimate",
        "objective": "maximize_projected_developer_profit_ils",
        "generated_at": generated_at.isoformat(),
        "compensation_sqm_per_existing_unit": optimization.compensation_sqm_per_existing_unit,
        "compensation_source": optimization.compensation_source,
        "default_compensation_status": assumptions.tenant_compensation_sqm_per_existing_unit.status.value,
        "default_compensation_source": assumptions.tenant_compensation_sqm_per_existing_unit.source,
        "unit_area_assumption_status": "estimate",
        "unit_area_assumption_source": UNIT_AREA_ASSUMPTION_SOURCE,
        "economic_assumptions_version": assumptions_version,
        "existing_units_basis": existing_units_basis,
        "average_existing_unit_sqm": round(sum(existing_areas) / len(existing_areas), 2),
        "sale_price_per_sqm_ils": sale_price,
        "sale_price_status": "estimate",
        "sale_price_source": block_label or assumptions.sale_price_per_sqm_ils.source,
        "tenant_units": best.tenant_units,
        "developer_units": best.developer_units,
        "unused_developer_sqm": best.unused_developer_sqm,
        "developer_available_sqm": optimization.developer_available_sqm,
        "warnings": optimization.warnings,
        "projected_profit_ils": best.projected_profit_ils,
        "profit_margin_on_cost_ratio": best.profit_margin_on_cost_ratio,
    }

    if persist:
        opportunity.metadata_json = {
            **(opportunity.metadata_json or {}),
            "planned_unit_mix": planned_mix,
            "planned_unit_mix_meta": metadata,
        }

        await session.flush()

    return PreparedUnitMix(
        result=optimization,
        planned_unit_mix=planned_mix,
        metadata=metadata,
    )
