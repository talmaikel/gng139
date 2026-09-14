from datetime import date, datetime, timezone

from app.cities.herzliya.dossier import _market_sale_price
from app.services.economic.assumptions import get_assumptions
from app.services.market_data.schemas import MarketValuation, ValuationStatus


def _valuation(*, blended: float | None, adjusted: bool) -> MarketValuation:
    return MarketValuation(
        status=ValuationStatus.ESTIMATED,
        as_of_date=date(2026, 9, 14),
        fetched_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        lookback_months=12,
        radius_m=500,
        comparable_count=12,
        comparable_sales=[],
        room_estimates=[],
        blended_price_per_sqm_ils=blended,
        is_unit_mix_adjusted=adjusted,
    )


def test_b10_uses_local_blended_market_price_when_unit_mix_is_explicit() -> None:
    assumptions = get_assumptions("herzliya")
    value, reported = _market_sale_price(
        assumptions,
        _valuation(blended=52_345.0, adjusted=True),
    )

    assert value == 52_345.0
    assert reported["value"] == 52_345.0
    assert reported["status"] == "estimate"
    assert reported["method"] == "local_comparable_sales_weighted_by_explicit_unit_mix"
    assert reported["source"] == "https://www.govmap.gov.il/?lay=nadlan"
    assert reported["as_of_date"] == "2026-09-14"


def test_b10_does_not_invent_project_price_without_complete_unit_mix() -> None:
    assumptions = get_assumptions("herzliya")
    value, reported = _market_sale_price(
        assumptions,
        _valuation(blended=None, adjusted=False),
    )

    assert value == assumptions.sale_price_per_sqm_ils.value
    assert reported["value"] == assumptions.sale_price_per_sqm_ils.value
    assert reported["method"] == "versioned_city_fallback_no_fresh_complete_unit_mix"


def test_b10_keeps_city_fallback_when_no_market_snapshot_exists() -> None:
    assumptions = get_assumptions("herzliya")
    value, reported = _market_sale_price(assumptions, None)

    assert value == assumptions.sale_price_per_sqm_ils.value
    assert reported["method"] == "versioned_city_fallback_no_fresh_complete_unit_mix"
