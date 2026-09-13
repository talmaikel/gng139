"""נתיב הקריאה של הראיות — הצד שאיש לא בדק עד A9.

‏`usable()` ו-`resolve_evidence()` היו קיימות ונכונות, אבל שום דבר לא קרא
שורות `FieldEvidence` בחזרה, ולכן בדיקת הגיל וזיהוי הסתירה מעולם לא פעלו
על נתון אמיתי. הבדיקות כאן מפעילות אותן.
"""
from datetime import datetime, timedelta, timezone

from app.evidence import Certainty, evidence, resolve_evidence, usable

NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)


def _field(days_old=1, certainty=Certainty.OFFICIAL, value=2265, location="גוש 6424 חלקה 144"):
    return evidence(value,
                    source={"url": "https://open.govmap.gov.il/x",
                            "retrieved_at": (NOW - timedelta(days=days_old)).isoformat()},
                    certainty=certainty, location=location)


def test_a_fresh_official_field_decides():
    assert usable(_field(1), now=NOW)


def test_the_thirty_first_day_stops_it_deciding():
    assert usable(_field(29), now=NOW)
    assert not usable(_field(31), now=NOW)


def test_a_field_without_a_location_never_decides():
    assert not usable(_field(location=None), now=NOW)


def test_an_ocr_reading_never_decides_however_fresh():
    assert not usable(_field(0, Certainty.OCR_CANDIDATE), now=NOW)
    assert not usable(_field(0, Certainty.COMMUNITY), now=NOW)


def test_two_sources_that_disagree_become_a_conflict_and_decide_nothing():
    r = resolve_evidence([_field(value=2265), _field(value=2300)])
    assert r["certainty"] == "conflict"
    assert len(r["observations"]) == 2     # שתיהן נשמרות, אף אחת לא נדרסת
    assert not usable(r, now=NOW)


def test_two_sources_that_agree_keep_the_value():
    r = resolve_evidence([_field(value=2265), _field(value=2265)])
    assert r["value"] == 2265
    assert usable(r, now=NOW)


# ── הנתיב דרך בסיס הנתונים ──
#
# כל מה שלמעלה עובד על dict. השורות עצמן נקראות ב-`fields_for`, ושם יושבות
# שתי החלטות שאי אפשר לבדוק בלעדיו: איחוד תצפיות לשדה אחד, וההפרדה בין
# ראיה על החלקה לראיה על מבנה מסוים בתוכה.

import pytest
from sqlalchemy import select

from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel
from app.services.evidence_store import deciding, fields_for, stale_fields

SQUARE = ("MULTIPOLYGON(((34.8420000 32.1620000,34.8424000 32.1620000,"
          "34.8424000 32.1623000,34.8420000 32.1623000,34.8420000 32.1620000)))")


async def _opp(session, block):
    o = Opportunity(city_code="herzliya", address=f"רחוב הבדיקה {block}", block=block,
                    block_suffix=0, parcel="1", geom=f"SRID=4326;{SQUARE}",
                    verification_level=VerificationLevel.RAW.value, metadata_json={})
    session.add(o)
    await session.flush()
    return o


def _row(oid, field, value, days_old=1, certainty=Certainty.OFFICIAL, url="https://a.test/x"):
    return FieldEvidence(opportunity_id=oid, field=field, value=value,
                         certainty=certainty.value, source_url=url,
                         retrieved_at=datetime.now(timezone.utc) - timedelta(days=days_old),
                         location="גוש בדיקה חלקה 1")


@pytest.mark.asyncio
async def test_two_rows_that_agree_become_one_deciding_field(session):
    o = await _opp(session, "9201")
    session.add_all([_row(o.id, "parcel_area", 1816, url="https://a.test/1"),
                     _row(o.id, "parcel_area", 1816, url="https://a.test/2")])
    await session.flush()
    assert deciding(await fields_for(session, o.id))["parcel_area"] == 1816


@pytest.mark.asyncio
async def test_two_rows_that_disagree_decide_nothing(session):
    """הכתיבה האחרונה אינה מנצחת. סתירה נשמרת כסתירה, והשדה יוצא מהמשחק."""
    o = await _opp(session, "9202")
    session.add_all([_row(o.id, "parcel_area", 1816, url="https://a.test/1"),
                     _row(o.id, "parcel_area", 2300, url="https://a.test/2")])
    await session.flush()
    f = await fields_for(session, o.id)
    assert f["parcel_area"]["certainty"] == "conflict"
    assert f["parcel_area"]["value"] is None
    assert "parcel_area" not in deciding(f)


@pytest.mark.asyncio
async def test_a_stale_row_is_named_before_it_breaks_anything(session):
    o = await _opp(session, "9203")
    session.add_all([_row(o.id, "parcel_area", 1816, days_old=400),
                     _row(o.id, "units", 28, days_old=1)])
    await session.flush()
    f = await fields_for(session, o.id)
    assert stale_fields(f) == ["parcel_area"]
    assert "parcel_area" not in deciding(f) and "units" in deciding(f)


@pytest.mark.asyncio
async def test_a_row_that_cannot_decide_for_another_reason_is_not_called_stale(session):
    """‏`stale_fields` היא אזהרת גיל. ראיית OCR אינה ישנה — היא פשוט אינה
    רשאית להכריע, ולערבב את השניים פירושו לשלוח אדם לרענן מקור טרי."""
    o = await _opp(session, "9204")
    session.add(_row(o.id, "floors", 4, certainty=Certainty.OCR_CANDIDATE))
    await session.flush()
    f = await fields_for(session, o.id)
    assert stale_fields(f) == []
    assert "floors" not in deciding(f)


@pytest.mark.asyncio
async def test_parcel_level_evidence_is_not_mixed_with_a_buildings(session):
    """ראיה על מבנה מסוים נושאת `building_id`. ברירת המחדל היא רמת החלקה,
    ובלי ההפרדה שתי קומות של שני מבנים היו נראות כסתירה."""
    o = await _opp(session, "9205")
    session.add(_row(o.id, "floors", 4))
    await session.flush()
    assert set(await fields_for(session, o.id)) == {"floors"}
