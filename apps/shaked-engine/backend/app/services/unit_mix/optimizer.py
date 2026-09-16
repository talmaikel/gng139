from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import ceil, floor

from app.services.economic.calculator import calculate_feasibility
from app.services.unit_mix.schemas import (
    UnitMixCandidate,
    UnitMixOptimizationInput,
    UnitMixOptimizationResult,
)


def _resolved_compensation(inputs: UnitMixOptimizationInput) -> tuple[float, str]:
    if inputs.compensation_sqm_per_existing_unit is not None:
        return inputs.compensation_sqm_per_existing_unit, "user_defined"
    return inputs.default_compensation_sqm_per_existing_unit, inputs.default_compensation_label


def _is_small(area_sqm: float, inputs: UnitMixOptimizationInput) -> bool:
    p = inputs.policy
    return p.small_unit_min_sqm <= area_sqm <= p.small_unit_max_sqm


def _is_micro(area_sqm: float, inputs: UnitMixOptimizationInput) -> bool:
    return area_sqm <= inputs.policy.micro_unit_max_sqm


def _count_ranges(inputs: UnitMixOptimizationInput, tenant_units: int) -> tuple[int, int]:
    p = inputs.policy
    minimum_total = ceil(tenant_units * p.min_unit_multiplier)
    maximum_total = floor(tenant_units * p.max_unit_multiplier)
    return minimum_total, maximum_total


@dataclass(frozen=True)
class _Base:
    """What every candidate shares: the owners' side of the building."""

    compensation: float
    tenant_units: int
    tenant_allocation: float
    developer_available: float
    tenant_small: int
    tenant_micro: int
    average_existing: float


def _base(inputs: UnitMixOptimizationInput) -> _Base:
    compensation, _ = _resolved_compensation(inputs)
    tenant_new_areas = [area + compensation for area in inputs.existing_unit_areas_sqm]
    tenant_allocation = sum(tenant_new_areas)
    return _Base(
        compensation=compensation,
        tenant_units=len(tenant_new_areas),
        tenant_allocation=tenant_allocation,
        developer_available=inputs.buildable_area_sqm * inputs.main_area_ratio - tenant_allocation,
        tenant_small=sum(_is_small(area, inputs) for area in tenant_new_areas),
        tenant_micro=sum(_is_micro(area, inputs) for area in tenant_new_areas),
        average_existing=sum(inputs.existing_unit_areas_sqm) / len(tenant_new_areas),
    )


def _shares(inputs: UnitMixOptimizationInput, base: _Base, counts_tuple) -> tuple[float, float]:
    options = inputs.unit_types
    total_units = base.tenant_units + sum(counts_tuple)
    small = base.tenant_small + sum(
        count for count, option in zip(counts_tuple, options) if _is_small(option.area_sqm, inputs))
    micro = base.tenant_micro + sum(
        count for count, option in zip(counts_tuple, options) if _is_micro(option.area_sqm, inputs))
    return small / total_units, micro / total_units


def _candidate(inputs: UnitMixOptimizationInput, base: _Base, counts_tuple) -> UnitMixCandidate | None:
    """One mix through Generic Report 0 -- the same pricing for the optimizer and a typed mix."""
    options = inputs.unit_types
    developer_units = sum(counts_tuple)
    total_units = base.tenant_units + developer_units
    used_area = sum(count * option.area_sqm for count, option in zip(counts_tuple, options))
    gross_revenue = sum(
        count * option.area_sqm * option.price_per_sqm_ils
        for count, option in zip(counts_tuple, options)
    )
    if used_area <= 0 or gross_revenue <= 0 or total_units == 0:
        return None

    small_units = base.tenant_small + sum(
        count for count, option in zip(counts_tuple, options) if _is_small(option.area_sqm, inputs))
    micro_units = base.tenant_micro + sum(
        count for count, option in zip(counts_tuple, options) if _is_micro(option.area_sqm, inputs))
    blended_price = gross_revenue / used_area
    economic_input = inputs.economic_input.model_copy(
        update={
            "average_existing_unit_sqm": base.average_existing,
            "tenant_compensation_sqm_per_existing_unit": base.compensation,
            "sale_price_per_sqm": blended_price,
            "developer_sale_revenue_ils": gross_revenue,
        }
    )
    economics = calculate_feasibility(
        economic_input,
        missing_inputs=inputs.economic_missing_inputs,
    )
    return UnitMixCandidate(
        counts={option.key: count for option, count in zip(options, counts_tuple) if count},
        total_new_units=total_units,
        developer_units=developer_units,
        tenant_units=base.tenant_units,
        tenant_allocation_sqm=round(base.tenant_allocation, 2),
        developer_used_sqm=round(used_area, 2),
        developer_available_sqm=round(base.developer_available, 2),
        unused_developer_sqm=round(base.developer_available - used_area, 2),
        small_units=small_units,
        micro_units=micro_units,
        small_unit_share=round(small_units / total_units, 4),
        micro_unit_share=round(micro_units / total_units, 4),
        gross_developer_revenue_ils=round(gross_revenue, 2),
        blended_sale_price_per_sqm_ils=round(blended_price, 2),
        developer_revenue_ils=economics.developer_revenue_ils,
        total_cost_ils=economics.total_cost_ils,
        projected_profit_ils=economics.projected_profit_ils,
        profit_margin_on_cost_ratio=economics.profit_margin_on_cost_ratio,
        meets_developer_target=economics.meets_developer_target,
        economics_deliverable=economics.is_deliverable,
    )


def evaluate_mix(
    inputs: UnitMixOptimizationInput, counts: dict[str, int]
) -> tuple[UnitMixCandidate | None, list[str]]:
    """W8: a mix the developer typed, priced exactly like an optimizer candidate.

    A mix that does not fit the developer's area is refused (``None`` and the
    reason). Herzliya's numeric constraints come back as warnings instead: a
    developer may test a mix the local committee would ask to change, as long
    as the screen says so.
    """
    options = inputs.unit_types
    unknown = sorted(set(counts) - {option.key for option in options})
    if unknown:
        raise ValueError(f"unknown unit types: {unknown}")
    counts_tuple = tuple(int(counts.get(option.key, 0)) for option in options)
    base = _base(inputs)
    if base.developer_available < 0:
        return None, [
            f"דירות הבעלים עם התמורה ({base.tenant_allocation:,.0f} מ״ר) אינן נכנסות בשטח העיקרי "
            f"הזמין ({inputs.buildable_area_sqm * inputs.main_area_ratio:,.0f} מ״ר), ולכן אין שטח ליזם."
        ]
    used_area = sum(count * option.area_sqm for count, option in zip(counts_tuple, options))
    if used_area > base.developer_available + 1e-9:
        return None, [
            f"התמהיל אינו נכנס בשטח ליזם: {used_area:,.0f} מ״ר בתמהיל, ו-{base.developer_available:,.0f} מ״ר "
            f"זמינים ליזם ({inputs.buildable_area_sqm:,.0f} מ״ר בנוי × {inputs.main_area_ratio:.0%} עיקרי, "
            f"פחות {base.tenant_allocation:,.0f} מ״ר לבעלי הדירות)."
        ]
    candidate = _candidate(inputs, base, counts_tuple)
    if candidate is None:
        return None, ["בתמהיל אין דירות ליזם."]

    p = inputs.policy
    problems: list[str] = []
    minimum_total, maximum_total = _count_ranges(inputs, base.tenant_units)
    if not minimum_total <= candidate.total_new_units <= maximum_total:
        problems.append(
            f"מכפיל הדירות: {candidate.total_new_units} דירות בבניין החדש, והמדיניות מתירה "
            f"{minimum_total}–{maximum_total} ({p.min_unit_multiplier:g}–{p.max_unit_multiplier:g} "
            f"× {base.tenant_units} הדירות הקיימות)."
        )
    if candidate.small_unit_share + 1e-12 < p.min_small_unit_share:
        problems.append(
            f"דירות קטנות ({p.small_unit_min_sqm:g}–{p.small_unit_max_sqm:g} מ״ר): "
            f"{candidate.small_unit_share:.0%} מהדירות, והמדיניות דורשת לפחות {p.min_small_unit_share:.0%}."
        )
    if candidate.micro_unit_share - 1e-12 > p.max_micro_unit_share:
        problems.append(
            f"דירות מיקרו (עד {p.micro_unit_max_sqm:g} מ״ר): {candidate.micro_unit_share:.0%} מהדירות, "
            f"והמדיניות מתירה עד {p.max_micro_unit_share:.0%}."
        )
    return candidate, problems


def optimize_unit_mix(inputs: UnitMixOptimizationInput) -> UnitMixOptimizationResult:
    """Enumerate Herzliya-compliant mixes and rank them by Report-0 profit.

    B15 does not repeat B3/B6 extraction or B16 market acquisition. It consumes
    those outputs, applies the developer's compensation choice, enumerates
    feasible mixes and then sends every candidate through the existing Generic
    Report 0 cost model. The candidate's room-sensitive apartment revenue is
    passed as an exact override, so unsold residual sqm is not counted as an
    imaginary apartment.
    """

    compensation, compensation_source = _resolved_compensation(inputs)
    tenant_new_areas = [area + compensation for area in inputs.existing_unit_areas_sqm]
    tenant_units = len(tenant_new_areas)
    tenant_allocation = sum(tenant_new_areas)
    total_main_area = inputs.buildable_area_sqm * inputs.main_area_ratio
    developer_available = total_main_area - tenant_allocation

    warnings = [
        "מדיניות הרצליה קובעת שבקומה טיפוסית יהיו בעיקר דירות 3 ו-4 חדרים, בלי סף מספרי; "
        "התמהיל אינו ממציא סף, ונדרשת בדיקה אדריכלית.",
        "דרישת 10% הדירות הנגישות היא דרישת תכנון ולא גודל דירה נפרד, ולכן אינה נספרת פעמיים בתמהיל.",
    ]

    if inputs.economic_missing_inputs:
        warnings.append(
            "בדוח 0 עדיין חסרים קלטים כלכליים: אפשר להשוות בין תמהילים, "
            "אבל התרחיש אינו נמסר כתוצאה עד שיושלמו."
        )

    if developer_available < 0:
        return UnitMixOptimizationResult(
            compensation_sqm_per_existing_unit=compensation,
            compensation_source=compensation_source,
            tenant_allocation_sqm=round(tenant_allocation, 2),
            total_main_area_sqm=round(total_main_area, 2),
            developer_available_sqm=round(developer_available, 2),
            feasible=False,
            warnings=warnings + ["דירות הבעלים עם התמורה אינן נכנסות בשטח העיקרי הזמין."],
        )

    min_total_units, max_total_units = _count_ranges(inputs, tenant_units)
    min_developer_units = max(0, min_total_units - tenant_units)
    max_developer_units = max(0, max_total_units - tenant_units)

    base = _base(inputs)
    options = inputs.unit_types
    per_type_caps = [
        min(max_developer_units, floor(developer_available / option.area_sqm))
        for option in options
    ]

    candidates: list[UnitMixCandidate] = []

    for counts_tuple in product(*(range(cap + 1) for cap in per_type_caps)):
        developer_units = sum(counts_tuple)
        if developer_units < min_developer_units or developer_units > max_developer_units:
            continue

        used_area = sum(count * option.area_sqm for count, option in zip(counts_tuple, options))
        if used_area > developer_available + 1e-9:
            continue

        total_units = tenant_units + developer_units
        if total_units == 0:
            continue

        small_share, micro_share = _shares(inputs, base, counts_tuple)
        p = inputs.policy
        if small_share + 1e-12 < p.min_small_unit_share:
            continue
        if micro_share - 1e-12 > p.max_micro_unit_share:
            continue

        candidate = _candidate(inputs, base, counts_tuple)
        if candidate is not None:
            candidates.append(candidate)

    # Product decision: primary objective is absolute developer profit. Profit
    # on cost is the first tie-breaker, followed by exact developer revenue and
    # lower unused residual area. This matches the B15 brief while still
    # exposing margin so the UI can offer a "highest margin" alternative.
    #
    # 15.09: with one price per sqm for every size (see service._unit_types),
    # many mixes use the same area and tie on all four keys, and the winner was
    # whichever the enumeration produced first. The policy says "mainly 3 and
    # 4 rooms", so ties now go to fewer 5+ room apartments, then to more units.
    rooms_by_key = {option.key: option.rooms for option in options}
    candidates.sort(
        key=lambda c: (
            c.projected_profit_ils,
            c.profit_margin_on_cost_ratio,
            c.gross_developer_revenue_ils,
            -c.unused_developer_sqm,
            -sum(n for k, n in c.counts.items() if rooms_by_key[k] >= 5),
            c.total_new_units,
        ),
        reverse=True,
    )
    candidates = candidates[: inputs.max_results]

    if not candidates:
        warnings.append(
            "אין תמהיל שעומד יחד בשטח, במכפיל הדירות, ב-25% הדירות הקטנות ובתקרת דירות המיקרו."
        )

    return UnitMixOptimizationResult(
        compensation_sqm_per_existing_unit=compensation,
        compensation_source=compensation_source,
        tenant_allocation_sqm=round(tenant_allocation, 2),
        total_main_area_sqm=round(total_main_area, 2),
        developer_available_sqm=round(developer_available, 2),
        feasible=bool(candidates),
        candidates=candidates,
        warnings=warnings,
    )
