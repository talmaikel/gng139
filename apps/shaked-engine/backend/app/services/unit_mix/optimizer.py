from __future__ import annotations

from itertools import product
from math import ceil, floor

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


def optimize_unit_mix(inputs: UnitMixOptimizationInput) -> UnitMixOptimizationResult:
    """Enumerate policy-compliant developer mixes and rank by gross revenue.

    This is deliberately a small, deterministic beta optimiser. It consumes
    existing B3/B6 and B16 outputs and does not repeat scraping or valuation.
    Full Report-0 profit ranking can be layered on top because construction
    costs are project-wide while this service resolves the apartment mix and
    its room-sensitive sales revenue.
    """

    compensation, compensation_source = _resolved_compensation(inputs)
    tenant_new_areas = [area + compensation for area in inputs.existing_unit_areas_sqm]
    tenant_units = len(tenant_new_areas)
    tenant_allocation = sum(tenant_new_areas)
    total_main_area = inputs.buildable_area_sqm * inputs.main_area_ratio
    developer_available = total_main_area - tenant_allocation

    warnings = [
        "Herzliya policy says typical floors should contain mainly 3- and 4-room apartments, "
        "but gives no numeric threshold; B15 does not invent one. Architectural review is required.",
        "The 10% accessibility requirement is a design requirement, not a separate apartment-size bucket; "
        "B15 does not double-count it in the numerical mix.",
    ]

    if developer_available < 0:
        return UnitMixOptimizationResult(
            compensation_sqm_per_existing_unit=compensation,
            compensation_source=compensation_source,
            tenant_allocation_sqm=round(tenant_allocation, 2),
            total_main_area_sqm=round(total_main_area, 2),
            developer_available_sqm=round(developer_available, 2),
            feasible=False,
            warnings=warnings + ["Existing tenants plus compensation do not fit in the available main area."],
        )

    min_total_units, max_total_units = _count_ranges(inputs, tenant_units)
    min_developer_units = max(0, min_total_units - tenant_units)
    max_developer_units = max(0, max_total_units - tenant_units)

    tenant_small = sum(_is_small(area, inputs) for area in tenant_new_areas)
    tenant_micro = sum(_is_micro(area, inputs) for area in tenant_new_areas)

    options = inputs.unit_types
    # A safe finite bound for every type: neither policy unit cap nor area can
    # permit more than this many units of a single type.
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

        developer_small = sum(
            count for count, option in zip(counts_tuple, options) if _is_small(option.area_sqm, inputs)
        )
        developer_micro = sum(
            count for count, option in zip(counts_tuple, options) if _is_micro(option.area_sqm, inputs)
        )
        small_units = tenant_small + developer_small
        micro_units = tenant_micro + developer_micro
        small_share = small_units / total_units
        micro_share = micro_units / total_units

        p = inputs.policy
        if small_share + 1e-12 < p.min_small_unit_share:
            continue
        if micro_share - 1e-12 > p.max_micro_unit_share:
            continue

        revenue = sum(
            count * option.area_sqm * option.price_per_sqm_ils
            for count, option in zip(counts_tuple, options)
        )
        candidates.append(
            UnitMixCandidate(
                counts={option.key: count for option, count in zip(options, counts_tuple) if count},
                total_new_units=total_units,
                developer_units=developer_units,
                tenant_units=tenant_units,
                tenant_allocation_sqm=round(tenant_allocation, 2),
                developer_used_sqm=round(used_area, 2),
                developer_available_sqm=round(developer_available, 2),
                unused_developer_sqm=round(developer_available - used_area, 2),
                small_units=small_units,
                micro_units=micro_units,
                small_unit_share=round(small_share, 4),
                micro_unit_share=round(micro_share, 4),
                gross_developer_revenue_ils=round(revenue, 2),
            )
        )

    candidates.sort(
        key=lambda c: (
            c.gross_developer_revenue_ils,
            -c.unused_developer_sqm,
            c.developer_units,
        ),
        reverse=True,
    )
    candidates = candidates[: inputs.max_results]

    if not candidates:
        warnings.append(
            "No candidate mix satisfies the current area, unit-multiplier, small-unit and micro-unit constraints."
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
