from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.opportunity import Opportunity
from app.services.dwelling_units import load_units, resolve_existing_unit_area
from app.services.economic.assumptions import get_assumptions
from app.services.economic.construction_costs import (
    resolve_construction_cost_per_sqm,
    resolve_underground_cost_per_sqm,
)
from app.services.economic.schemas import FeasibilityInput
from app.services.market_data.repository import add_valuation_run, find_latest_valuation
from app.services.market_data.schemas import TargetUnit
from app.services.market_data.valuation import calculate_market_valuation
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
    floors = ((assessment.get("floors") or {}).get("low"))
    construction = resolve_construction_cost_per_sqm(
        opportunity.city_code, developer_value=None, floors=floors
    )
    underground = resolve_underground_cost_per_sqm(opportunity.city_code)

    blocking = [
        key
        for key in a.blocking()
        if key not in {
            "average_existing_unit_sqm",  # full per-unit schedule is required below
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
    # Candidate-specific room prices replace this placeholder inside the
    # optimizer. It still has to be a valid positive FeasibilityInput field.
    sale_price = a.sale_price_per_sqm_ils.value

    return (
        FeasibilityInput(
            plot_area_sqm=opportunity.area_sqm,
            existing_units=opportunity.existing_units,
            buildable_area_sqm=buildable_area_sqm,
            sale_price_per_sqm=sale_price,
            construction_cost_per_sqm=construction_cost,
            soft_cost_ratio=a.soft_cost_ratio.value,
            demolition_cost_per_unit=a.demolition_cost_per_unit_ils.value,
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


def _priced_unit_types(valuation) -> tuple[list[UnitTypeOption], dict[str, Any]]:
    """Re-price the beta apartment sizes from the already-fetched comparables.

    No request to GovMap is made here. The latest immutable valuation snapshot
    already carries the factual comparable sales, and B15 asks the existing
    valuation engine how those sales price 75/100/125 sqm apartments.
    """

    if not valuation or not valuation.comparable_sales:
        raise UnitMixUnavailable(
            "אין עסקאות השוואה שמורות לחלקה. יש להריץ את שלב B1/B16 לפני B15."
        )

    targets = [
        TargetUnit(rooms=rooms, area_sqm=area, units=1)
        for rooms, area in DEFAULT_UNIT_AREAS_SQM.items()
    ]
    repriced = calculate_market_valuation(
        valuation.comparable_sales,
        targets,
        as_of_date=valuation.as_of_date,
        lookback_months=valuation.lookback_months,
        radius_m=valuation.radius_m,
        fetched_at=valuation.fetched_at,
    )

    options: list[UnitTypeOption] = []
    room_evidence: dict[str, Any] = {}
    for target, estimate in zip(targets, repriced.room_estimates, strict=True):
        room = int(target.rooms)
        room_evidence[str(room)] = {
            "area_sqm": target.area_sqm,
            "comparable_count": estimate.comparable_count,
            "base_price_per_sqm_ils": estimate.base_price_per_sqm_ils,
            "confidence": estimate.confidence.value,
        }
        if estimate.base_price_per_sqm_ils is None:
            continue
        options.append(
            UnitTypeOption(
                key=f"{room}r",
                rooms=target.rooms,
                area_sqm=target.area_sqm,
                price_per_sqm_ils=estimate.base_price_per_sqm_ils,
            )
        )

    if not options:
        raise UnitMixUnavailable("אין אף קבוצת חדרים עם עסקאות השוואה תקינות.")
    if not any(56 <= option.area_sqm <= 80 for option in options):
        raise UnitMixUnavailable(
            "אין קבוצת דירות מתומחרת בטווח 56–80 מ״ר, ולכן אי אפשר לקיים את דרישת 25% הדירות הקטנות."
        )
    return options, room_evidence


async def prepare_unit_mix(
    session: AsyncSession,
    opportunity: Opportunity,
    *,
    compensation_sqm_per_existing_unit: float | None,
    persist: bool = True,
) -> PreparedUnitMix:
    """Run B15 from the opportunity's existing B3/B16/Report-0 inputs.

    If ``persist`` is true, the recommended mix is written to
    ``opportunity.metadata_json['planned_unit_mix']`` and an immutable,
    mix-adjusted valuation snapshot is added from the *already stored*
    comparable sales. The dossier can therefore consume the transaction-based
    blended price immediately, without a network call at read time.
    """

    if opportunity.city_code != "herzliya":
        raise UnitMixUnavailable("B15 beta currently supports Herzliya only.")
    if not opportunity.existing_units or not opportunity.area_sqm:
        raise UnitMixUnavailable("חסרים מספר דירות קיים או שטח מגרש.")

    assessment = _assessment(opportunity)
    buildable = assessment.get("cap_400_sqm")
    if not buildable or buildable <= 0:
        raise UnitMixUnavailable("אין תקרת זכויות מבוססת לחלקה.")

    units = await load_units(session, opportunity.id)
    resolution = resolve_existing_unit_area(
        units,
        municipal_unit_count=opportunity.existing_units,
        existing_area_sqm=None,
    )
    if not resolution.per_unit_detail_available:
        raise UnitMixUnavailable(
            "חישוב תמורה לכל בעל דירה דורש לוח דירות מלא ומאומת; ממוצע בניין אינו מספיק."
        )
    verified_units = [
        unit for unit in units
        if not unit.requires_human_review and unit.area_sqm is not None
    ]
    existing_areas = [float(unit.area_sqm) for unit in verified_units]
    if len(existing_areas) != opportunity.existing_units:
        raise UnitMixUnavailable("לוח הדירות המאומת אינו מכסה את כל הדירות הקיימות.")

    assumptions = get_assumptions(opportunity.city_code)
    default_comp = assumptions.tenant_compensation_sqm_per_existing_unit.value
    compensation = (
        compensation_sqm_per_existing_unit
        if compensation_sqm_per_existing_unit is not None
        else default_comp
    )

    latest = await find_latest_valuation(
        session,
        opportunity_id=opportunity.id,
        max_age_days=get_settings().source_max_age_days,
    )
    options, room_evidence = _priced_unit_types(latest)

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
        "room_market_evidence": room_evidence,
        "market_as_of_date": str(latest.as_of_date),
        "market_comparable_count": latest.comparable_count,
        "market_radius_m": latest.radius_m,
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

        targets = [TargetUnit.model_validate(item) for item in planned_mix]
        adjusted = calculate_market_valuation(
            latest.comparable_sales,
            targets,
            as_of_date=latest.as_of_date,
            lookback_months=latest.lookback_months,
            radius_m=latest.radius_m,
            fetched_at=generated_at,
        )
        if not adjusted.is_unit_mix_adjusted or adjusted.blended_price_per_sqm_ils is None:
            raise UnitMixUnavailable(
                "התמהיל נוצר, אבל אין מספיק עסקאות כדי לחשב לו מחיר משוקלל."
            )
        add_valuation_run(
            session,
            opportunity_id=opportunity.id,
            valuation=adjusted,
            parameters={
                "unit_mix_state": "provided",
                "targets": [target.model_dump(mode="json") for target in targets],
                "source": "b15_profit_optimizer",
            },
        )
        await session.flush()

    return PreparedUnitMix(
        result=optimization,
        planned_unit_mix=planned_mix,
        metadata=metadata,
    )
