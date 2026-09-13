"""
Parcel identity and buildings (migration 0003) against a real, migrated Postgres.
Runs in a rolled-back transaction; skips when the database is not at 0003.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.evidence import Certainty
from app.models.building import Building
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

pytestmark = pytest.mark.db

PARCEL_GEOM = "SRID=4326;MULTIPOLYGON(((34.8390 32.1683,34.8396 32.1683,34.8396 32.1688,34.8390 32.1688,34.8390 32.1683)))"


@pytest.fixture
async def db(session):
    if not (await session.execute(text("SELECT to_regclass('public.buildings') IS NOT NULL"))).scalar():
        pytest.skip("database not migrated to 0003")
    return session


def parcel(suffix: int = 0) -> Opportunity:
    return Opportunity(
        city_code="herzliya", address="השושנים 4, הרצליה", block="6529", block_suffix=suffix, parcel="167", geom=PARCEL_GEOM
    )


def fact(opportunity_id, field, value, building_id=None) -> FieldEvidence:
    return FieldEvidence(
        opportunity_id=opportunity_id,
        building_id=building_id,
        field=field,
        value=value,
        certainty=Certainty.OFFICIAL,
        source_url="https://example.org",
        retrieved_at=datetime.now(timezone.utc),
        location="test",
    )


async def _count(db, model, *where) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_a_parcel_is_stored_once_per_city(db):
    db.add(parcel())
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(parcel())
            await db.flush()


async def test_a_different_sub_gush_suffix_is_a_different_parcel(db):
    db.add_all([parcel(suffix=0), parcel(suffix=2)])
    await db.flush()
    assert await _count(db, Opportunity, Opportunity.block == "6529", Opportunity.parcel == "167") == 2


async def test_the_same_building_source_cannot_be_added_twice_to_one_parcel(db):
    opportunity = parcel()
    db.add(opportunity)
    await db.flush()
    db.add(Building(opportunity_id=opportunity.id, source_key="osm:way:385608705"))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Building(opportunity_id=opportunity.id, source_key="osm:way:385608705"))
            await db.flush()


async def test_building_evidence_goes_with_its_building_and_parcel_evidence_stays(db):
    opportunity = parcel()
    db.add(opportunity)
    await db.flush()
    building = Building(opportunity_id=opportunity.id, source_key="municipal-file:5848")
    db.add(building)
    await db.flush()
    db.add_all([fact(opportunity.id, "units", 6, building.id), fact(opportunity.id, "parcel_area", 704)])
    await db.flush()

    await db.execute(delete(Building).where(Building.id == building.id))
    assert await _count(db, FieldEvidence, FieldEvidence.field == "units", FieldEvidence.opportunity_id == opportunity.id) == 0
    assert await _count(db, FieldEvidence, FieldEvidence.field == "parcel_area", FieldEvidence.opportunity_id == opportunity.id) == 1

    await db.execute(delete(Opportunity).where(Opportunity.id == opportunity.id))
    assert await _count(db, FieldEvidence, FieldEvidence.opportunity_id == opportunity.id) == 0
