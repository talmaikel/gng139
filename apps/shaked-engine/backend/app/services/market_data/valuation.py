from datetime import date, datetime, timezone

from app.services.market_data.schemas import (
    ComparableSale,
    Confidence,
    MarketValuation,
    RoomPriceEstimate,
    TargetUnit,
    ValuationStatus,
)


def _weighted_quantile(
    values_and_weights: list[tuple[float, float]], quantile: float
) -> float:
    ordered = sorted(values_and_weights)
    total_weight = sum(weight for _, weight in ordered)
    threshold = total_weight * quantile
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _iqr_filter(sales: list[ComparableSale]) -> list[ComparableSale]:
    if len(sales) < 4:
        return sales
    values = sorted(sale.price_per_sqm_ils for sale in sales)
    q1 = values[int((len(values) - 1) * 0.25)]
    q3 = values[int((len(values) - 1) * 0.75)]
    spread = q3 - q1
    lower, upper = q1 - 1.5 * spread, q3 + 1.5 * spread
    return [sale for sale in sales if lower <= sale.price_per_sqm_ils <= upper]


def _sale_weight(
    sale: ComparableSale,
    *,
    target: TargetUnit,
    as_of_date: date,
    lookback_months: int,
    radius_m: int,
) -> float:
    age_days = max(0, (as_of_date - sale.deal_date).days)
    recency = max(0.2, 1.0 - age_days / max(1, lookback_months * 30.4))
    distance = max(0.2, 1.0 - (sale.distance_m or radius_m) / max(1, radius_m))
    room_similarity = 1.0 if sale.rooms == target.rooms else 0.7
    area_similarity = 1.0
    if target.area_sqm:
        area_similarity = max(
            0.4, 1.0 - abs(sale.area_sqm - target.area_sqm) / target.area_sqm
        )
    return recency * distance * room_similarity * area_similarity


def _confidence(count: int, median_distance_m: float | None) -> Confidence:
    if count >= 8 and (median_distance_m is None or median_distance_m <= 500):
        return Confidence.HIGH
    if count >= 5:
        return Confidence.MEDIUM
    if count:
        return Confidence.LOW
    return Confidence.NONE


def _estimate_room(
    sales: list[ComparableSale],
    target: TargetUnit,
    *,
    as_of_date: date,
    lookback_months: int,
    radius_m: int,
) -> RoomPriceEstimate:
    room_matches = [sale for sale in sales if abs(sale.rooms - target.rooms) <= 0.5]
    area_matches = room_matches
    if target.area_sqm:
        similar_area = [
            sale
            for sale in room_matches
            if abs(sale.area_sqm - target.area_sqm) / target.area_sqm <= 0.20
        ]
        if len(similar_area) >= 5:
            area_matches = similar_area
    matches = _iqr_filter(area_matches)
    if not matches:
        return RoomPriceEstimate(
            rooms=target.rooms,
            target_area_sqm=target.area_sqm,
            target_units=target.units,
            comparable_count=0,
            confidence=Confidence.NONE,
        )

    weighted = [
        (
            sale.price_per_sqm_ils,
            _sale_weight(
                sale,
                target=target,
                as_of_date=as_of_date,
                lookback_months=lookback_months,
                radius_m=radius_m,
            ),
        )
        for sale in matches
    ]
    distances = sorted(
        sale.distance_m for sale in matches if sale.distance_m is not None
    )
    median_distance = distances[len(distances) // 2] if distances else None
    base = _weighted_quantile(weighted, 0.5)
    return RoomPriceEstimate(
        rooms=target.rooms,
        target_area_sqm=target.area_sqm,
        target_units=target.units,
        comparable_count=len(matches),
        low_price_per_sqm_ils=round(_weighted_quantile(weighted, 0.25), 2),
        base_price_per_sqm_ils=round(base, 2),
        high_price_per_sqm_ils=round(_weighted_quantile(weighted, 0.75), 2),
        estimated_total_price_ils=round(base * target.area_sqm, 2)
        if target.area_sqm
        else None,
        confidence=_confidence(len(matches), median_distance),
        comparable_deal_ids=[sale.source_deal_id for sale in matches],
    )


def calculate_market_valuation(
    sales: list[ComparableSale],
    targets: list[TargetUnit],
    *,
    as_of_date: date,
    lookback_months: int,
    radius_m: int,
    fetched_at: datetime | None = None,
) -> MarketValuation:
    fetched_at = fetched_at or datetime.now(timezone.utc)
    room_estimates = [
        _estimate_room(
            sales,
            target,
            as_of_date=as_of_date,
            lookback_months=lookback_months,
            radius_m=radius_m,
        )
        for target in targets
    ]

    usable_mix = bool(targets) and all(
        target.units and target.area_sqm for target in targets
    )
    blended = None
    if usable_mix and all(
        estimate.base_price_per_sqm_ils is not None for estimate in room_estimates
    ):
        total_area = sum(
            target.units * target.area_sqm
            for target in targets
            if target.units and target.area_sqm
        )
        blended = (
            sum(
                estimate.base_price_per_sqm_ils * target.units * target.area_sqm
                for target, estimate in zip(targets, room_estimates, strict=True)
                if target.units and target.area_sqm and estimate.base_price_per_sqm_ils
            )
            / total_area
        )

    warnings: list[str] = []
    if not usable_mix:
        warnings.append(
            "No explicit planned_unit_mix was supplied; room-level estimates are shown, but no project-wide price was invented."
        )
    missing_rooms = [
        str(estimate.rooms)
        for estimate in room_estimates
        if estimate.base_price_per_sqm_ils is None
    ]
    if missing_rooms:
        warnings.append(
            f"No valid comparable sales for room group(s): {', '.join(missing_rooms)}."
        )
    if sales:
        warnings.append(
            "This is an automated comparable-sales estimate, not a signed appraisal."
        )

    status = (
        ValuationStatus.ESTIMATED
        if sales and any(estimate.base_price_per_sqm_ils for estimate in room_estimates)
        else ValuationStatus.INSUFFICIENT_DATA
    )
    return MarketValuation(
        status=status,
        as_of_date=as_of_date,
        fetched_at=fetched_at,
        lookback_months=lookback_months,
        radius_m=radius_m,
        comparable_count=len(sales),
        comparable_sales=sales,
        room_estimates=room_estimates,
        blended_price_per_sqm_ils=round(blended, 2) if blended is not None else None,
        is_unit_mix_adjusted=blended is not None,
        warnings=warnings,
    )
