from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.opportunity import Opportunity
from app.services.market_data.schemas import ComparableSale
from app.services.market_data.valuation import calculate_market_valuation
from app.services.unit_mix import service


class FakeSession:
    def __init__(self):
        self.flush_count = 0

    async def flush(self):
        self.flush_count += 1


def _sale(index: int, rooms: int, area: float, price_per_sqm: float) -> ComparableSale:
    return ComparableSale(
        source_deal_id=f"{rooms}-{index}",
        city_code="herzliya",
        deal_date=date(2026, 8, 1),
        deal_amount_ils=area * price_per_sqm,
        area_sqm=area,
        rooms=rooms,
        price_per_sqm_ils=price_per_sqm,
        distance_m=100 + index * 10,
    )


def _valuation():
    sales = []
    for i in range(6):
        sales.extend(
            [
                _sale(i, 3, 72 + i, 38_000 + i * 100),
                _sale(i, 4, 96 + i, 36_000 + i * 100),
                _sale(i, 5, 120 + i, 34_000 + i * 100),
            ]
        )
    # The input valuation is deliberately NOT mix-adjusted, which is the state
    # B15 exists to resolve for the dossier.
    return calculate_market_valuation(
        sales,
        [],
        as_of_date=date(2026, 9, 15),
        lookback_months=12,
        radius_m=500,
        fetched_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )


def _opportunity() -> Opportunity:
    return Opportunity(
        id=uuid4(),
        city_code="herzliya",
        address="בדיקת B15 1, הרצליה",
        geom="MULTIPOLYGON EMPTY",
        area_sqm=900,
        existing_units=6,
        metadata_json={
            "assessment": {
                "cap_400_sqm": 2400.0,
                "floors": {"low": 8, "high": 8},
            }
        },
    )


@pytest.mark.asyncio
async def test_prepare_unit_mix_uses_default_compensation_and_persists_auditable_mix(monkeypatch):
    opp = _opportunity()
    units = [SimpleNamespace(area_sqm=area, requires_human_review=False) for area in [65, 70, 75, 80, 85, 90]]
    valuation = _valuation()
    added = []

    async def fake_load_units(session, opportunity_id):
        return units

    async def fake_latest(session, *, opportunity_id, max_age_days):
        return valuation

    monkeypatch.setattr(service, "load_units", fake_load_units)
    monkeypatch.setattr(
        service,
        "resolve_existing_unit_area",
        lambda *args, **kwargs: SimpleNamespace(per_unit_detail_available=True),
    )
    monkeypatch.setattr(service, "find_latest_valuation", fake_latest)
    monkeypatch.setattr(service, "add_valuation_run", lambda *args, **kwargs: added.append(kwargs))

    session = FakeSession()
    prepared = await service.prepare_unit_mix(
        session,
        opp,
        compensation_sqm_per_existing_unit=None,
        persist=True,
    )

    assert prepared.result.compensation_sqm_per_existing_unit == 25.0
    assert prepared.result.compensation_source.startswith("market_default:")
    assert prepared.planned_unit_mix
    assert opp.metadata_json["planned_unit_mix"] == prepared.planned_unit_mix
    meta = opp.metadata_json["planned_unit_mix_meta"]
    assert meta["source"] == "b15_profit_optimizer"
    assert meta["status"] == "estimate"
    assert meta["unit_area_assumption_status"] == "estimate"
    assert meta["market_comparable_count"] == len(valuation.comparable_sales)
    assert meta["projected_profit_ils"] == prepared.result.candidates[0].projected_profit_ils
    assert session.flush_count == 1
    assert len(added) == 1
    assert added[0]["valuation"].is_unit_mix_adjusted is True
    assert added[0]["valuation"].blended_price_per_sqm_ils is not None


@pytest.mark.asyncio
async def test_user_compensation_recalculates_mix_without_fetching_new_market_data(monkeypatch):
    opp = _opportunity()
    units = [SimpleNamespace(area_sqm=area, requires_human_review=False) for area in [65, 70, 75, 80, 85, 90]]
    valuation = _valuation()

    async def fake_load_units(session, opportunity_id):
        return units

    async def fake_latest(session, *, opportunity_id, max_age_days):
        return valuation

    monkeypatch.setattr(service, "load_units", fake_load_units)
    monkeypatch.setattr(
        service,
        "resolve_existing_unit_area",
        lambda *args, **kwargs: SimpleNamespace(per_unit_detail_available=True),
    )
    monkeypatch.setattr(service, "find_latest_valuation", fake_latest)

    session = FakeSession()
    low = await service.prepare_unit_mix(
        session, opp, compensation_sqm_per_existing_unit=10, persist=False
    )
    high = await service.prepare_unit_mix(
        session, opp, compensation_sqm_per_existing_unit=20, persist=False
    )

    assert low.result.compensation_source == "user_defined"
    assert high.result.compensation_source == "user_defined"
    assert high.result.tenant_allocation_sqm - low.result.tenant_allocation_sqm == pytest.approx(60)
    assert high.result.developer_available_sqm < low.result.developer_available_sqm


@pytest.mark.asyncio
async def test_per_household_mix_refuses_an_unverified_or_partial_schedule(monkeypatch):
    opp = _opportunity()

    async def fake_load_units(session, opportunity_id):
        return [SimpleNamespace(area_sqm=70, requires_human_review=True)]

    monkeypatch.setattr(service, "load_units", fake_load_units)
    monkeypatch.setattr(
        service,
        "resolve_existing_unit_area",
        lambda *args, **kwargs: SimpleNamespace(per_unit_detail_available=False),
    )

    with pytest.raises(service.UnitMixUnavailable, match="לוח דירות מלא ומאומת"):
        await service.prepare_unit_mix(
            FakeSession(), opp, compensation_sqm_per_existing_unit=12, persist=False
        )
