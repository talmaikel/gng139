from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.opportunity import Opportunity
from app.services.unit_mix import service


class FakeSession:
    def __init__(self):
        self.flush_count = 0

    async def flush(self):
        self.flush_count += 1


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

    async def fake_load_units(session, opportunity_id):
        return units

    monkeypatch.setattr(service, "load_units", fake_load_units)
    monkeypatch.setattr(
        service,
        "resolve_existing_unit_area",
        lambda *args, **kwargs: SimpleNamespace(per_unit_detail_available=True),
    )

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
    assert meta["existing_units_basis"] == "confirmed_schedule"
    assert meta["projected_profit_ils"] == prepared.result.candidates[0].projected_profit_ils
    assert session.flush_count == 1
    # 15.09: no mix-adjusted valuation snapshot. FakeSession has no `add`, so
    # writing one would raise here; a second-hand price weighted by this mix
    # must not reach the dossier's sale price.


@pytest.mark.asyncio
async def test_user_compensation_recalculates_mix_without_fetching_new_market_data(monkeypatch):
    opp = _opportunity()
    units = [SimpleNamespace(area_sqm=area, requires_human_review=False) for area in [65, 70, 75, 80, 85, 90]]

    async def fake_load_units(session, opportunity_id):
        return units

    monkeypatch.setattr(service, "load_units", fake_load_units)
    monkeypatch.setattr(
        service,
        "resolve_existing_unit_area",
        lambda *args, **kwargs: SimpleNamespace(per_unit_detail_available=True),
    )

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
async def test_without_a_confirmed_schedule_the_mix_uses_the_building_average(monkeypatch):
    """15.09: 0 of 699 parcels had a confirmed schedule, so the screen never
    produced a mix. The owners' total area is n x (average + c) either way."""
    opp = _opportunity()

    async def fake_load_units(session, opportunity_id):
        return [SimpleNamespace(area_sqm=70, requires_human_review=True)]

    async def fake_fields(session, opportunity_id):
        return {"existing_area": {"value": 480.0}}

    monkeypatch.setattr(service, "load_units", fake_load_units)
    monkeypatch.setattr(service, "fields_for", fake_fields)
    monkeypatch.setattr(
        service,
        "resolve_existing_unit_area",
        lambda *args, **kwargs: SimpleNamespace(
            per_unit_detail_available=False,
            average_existing_unit_sqm=(kwargs["existing_area_sqm"] or 0) / 6 or None,
        ),
    )

    prepared = await service.prepare_unit_mix(
        FakeSession(), opp, compensation_sqm_per_existing_unit=12, persist=False
    )
    assert prepared.metadata["existing_units_basis"] == "building_average"
    assert prepared.metadata["average_existing_unit_sqm"] == 80.0
    assert prepared.result.tenant_allocation_sqm == pytest.approx(6 * (80 + 12))


def test_every_apartment_size_sells_at_the_dossier_price():
    """15.09: per-room second-hand prices put the mix screen at -17.6% while
    the dossier said +20.8% for the same parcel."""
    from app.services.economic.assumptions import get_assumptions

    price = get_assumptions("herzliya").sale_price_per_sqm_ils.value
    options = service._unit_types(price)
    assert {o.rooms for o in options} == {3, 4, 5}
    assert all(o.price_per_sqm_ils == price for o in options)
