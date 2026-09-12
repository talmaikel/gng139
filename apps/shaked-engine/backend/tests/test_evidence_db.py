"""
field_evidence against a real, migrated Postgres.

Each test runs inside a transaction that is rolled back, so nothing is left in
the database. Without a reachable, migrated database the tests are skipped
rather than failed, so the unit suite still runs on a machine with no Postgres.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.evidence import CONFLICT, Certainty, resolve_evidence, usable
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

pytestmark = pytest.mark.db

HASHOSHANIM_4 = "SRID=4326;MULTIPOLYGON(((34.8390 32.1683,34.8396 32.1683,34.8396 32.1688,34.8390 32.1688,34.8390 32.1683)))"


@pytest.fixture
async def session():
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM field_evidence LIMIT 0"))
    except Exception as exc:  # no server, no database, or not migrated
        await engine.dispose()
        pytest.skip(f"no migrated database reachable: {type(exc).__name__}")
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _opportunity(session) -> Opportunity:
    opportunity = Opportunity(city_code="herzliya", address="השושנים 4, הרצליה", block="6529", parcel="167", geom=HASHOSHANIM_4)
    session.add(opportunity)
    await session.flush()
    return opportunity


def _observation(opportunity_id, value, source_url, location, certainty=Certainty.OFFICIAL) -> FieldEvidence:
    return FieldEvidence(
        opportunity_id=opportunity_id,
        field="parcel_area",
        value=value,
        certainty=certainty,
        source_url=source_url,
        retrieved_at=datetime.now(timezone.utc),
        location=location,
        method="test",
    )


async def test_two_sources_that_disagree_are_both_kept_and_resolve_to_a_conflict(session):
    opportunity = await _opportunity(session)
    session.add_all(
        [
            _observation(opportunity.id, 704, "https://open.govmap.gov.il/geoserver/opendata/wfs", "Parcels_ITM.785443.LEGAL_AREA"),
            _observation(opportunity.id, 742, "https://handasi.complot.co.il/magicscripts/mgrqispi.dll", "building file header"),
        ]
    )
    await session.flush()
    rows = (
        await session.execute(
            select(FieldEvidence).where(FieldEvidence.opportunity_id == opportunity.id, FieldEvidence.field == "parcel_area")
        )
    ).scalars().all()
    field = resolve_evidence([row.as_observation() for row in rows])
    assert field["certainty"] == CONFLICT and not usable(field)
    assert sorted(o["value"] for o in field["observations"]) == [704, 742]


async def test_certainty_is_stored_as_its_value_not_its_member_name(session):
    # The same values_callable mistake broke every status column once (commit 3090fa3).
    opportunity = await _opportunity(session)
    session.add(_observation(opportunity.id, 128, "https://api.openai.com", "legend crop", Certainty.AI_CANDIDATE))
    await session.flush()
    stored = (
        await session.execute(text("SELECT certainty::text FROM field_evidence WHERE opportunity_id = :id"), {"id": opportunity.id})
    ).scalar_one()
    assert stored == "ai_candidate"


async def test_evidence_is_removed_with_its_opportunity(session):
    opportunity = await _opportunity(session)
    session.add(_observation(opportunity.id, 704, "https://open.govmap.gov.il", "Parcels_ITM.785443.LEGAL_AREA"))
    await session.flush()
    await session.execute(delete(Opportunity).where(Opportunity.id == opportunity.id))
    remaining = (
        await session.execute(select(func.count()).select_from(FieldEvidence).where(FieldEvidence.opportunity_id == opportunity.id))
    ).scalar_one()
    assert remaining == 0
