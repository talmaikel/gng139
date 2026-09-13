"""שרשרת הזכויות מקצה לקצה: שורות ראיה → שערים → הדגל שהלקוח רואה.

עד כאן נבדקו החלקים לחוד. הבדיקות כאן מפעילות את `assess()` ו-`refresh()`
על הזדמנות אמיתית בבסיס נתונים, כי שם נפלו שתי התקלות שהכי קשה לראות:
שדה שנקרא בשם אחר ממה שנכתב, ודגל שנמסר כ״מוכן״ בעוד ששער הסף שלו
מעולם לא נשאל.

הזהות סינתטית בכוונה — גוש 6529 חלקה 167 היא הששנים 4 האמיתית, והצמדת
בדיקות לחלקה קיימת שברה שבעה טסטים ביום שהיא נזרעה.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.cities.herzliya import rights
from app.cities.herzliya.assessments import DELIVERABLE, _threshold_open, refresh
from app.cities.herzliya.rules import HerzliyaCityRules, _scope_check, _status
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel

SQUARE = ("MULTIPOLYGON(((34.8400000 32.1600000,34.8404000 32.1600000,"
          "34.8404000 32.1603000,34.8400000 32.1603000,34.8400000 32.1600000)))")


async def _opportunity(session, block, **fields):
    """הזדמנות אחת עם שורת ראיה לכל שדה. הכול טרי ורשמי אלא אם נאמר אחרת."""
    opp = Opportunity(city_code="herzliya", address=f"רחוב הבדיקה {block}",
                      block=block, block_suffix=0, parcel="1",
                      geom=f"SRID=4326;{SQUARE}", area_sqm=1800.0, existing_units=28,
                      verification_level=VerificationLevel.RAW.value, metadata_json={})
    session.add(opp)
    await session.flush()
    now = datetime.now(timezone.utc)
    for field, value in fields.items():
        session.add(FieldEvidence(
            opportunity_id=opp.id, field=field, value=value,
            certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
            retrieved_at=now - timedelta(days=1), location=f"גוש {block} חלקה 1"))
    await session.flush()
    return opp


ANSWERED = dict(residential_zoning=True, permit_date="1978-01-01", strengthened=False,
                occupied=False, floors=4, units=28, scope_buildings=1,
                street_width=12.0, renewal_policy_category="התחדשות מגרשית מוטת מגורים",
                in_tama70=True, registration_area='שז"ר')


# ── סטטוס ──

def test_an_unanswered_gate_is_not_a_pass():
    C = rights.Check
    P = [C("a", "a", "passed", "u", 1), C("b", "b", "unknown", "u", 1)]
    assert _status(P) == "needs_verification"
    assert _status([P[0]]) == "eligible"


def test_a_failure_outranks_a_routing_and_a_routing_outranks_an_unknown():
    C = rights.Check
    fail, routed, unknown = (C("x", "x", s, "u", 1) for s in ("failed", "routed", "unknown"))
    assert _status([fail, routed, unknown]) == "ineligible"
    assert _status([routed, unknown]) == "urban_renewal_compound"


def test_three_buildings_are_routed_and_not_rejected():
    """מסלול המתחמים הוא כללי זכויות אחרים, לא פסילה."""
    assert _scope_check(1).status == "passed"
    assert _scope_check(2).status == "passed"
    assert _scope_check(3).status == "routed"
    assert _scope_check(0).status == "failed"
    assert _scope_check(None).status == "unknown"


# ── ‏assess() על ראיות אמיתיות ──

@pytest.mark.asyncio
async def test_assess_reads_the_fields_by_the_names_the_seeder_writes(session):
    """השם שנכתב והשם שנקרא הוא בדיוק המקום שבו 699 שורות נעלמו פעם בשקט."""
    opp = await _opportunity(session, "9001", **ANSWERED)
    a = await HerzliyaCityRules().assess(session, opp.id)
    unknown = {c["id"] for c in a["checks"] if c["status"] == "unknown"}
    assert unknown == {"residential_share"}          # ורק הוא — אין לו מקור פתוח
    assert a["status"] == "needs_verification"
    assert a["floors"]["low"] == 8                   # 12 מ׳ → שורת 12-15? לא: 10-12 → 8
    assert a["parking"]["per_unit"] == 1.0


@pytest.mark.asyncio
async def test_an_estimate_is_shown_and_never_decides(session):
    """שטח קיים הוא ESTIMATE. הוא מזין את תקרת 400% ואסור לו לפסול דבר."""
    opp = await _opportunity(session, "9002", **ANSWERED)
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="existing_area", value=2000.0,
        certainty=Certainty.ESTIMATE.value, source_url="https://example.test/x",
        retrieved_at=datetime.now(timezone.utc), location="גוש 9002"))
    await session.flush()
    a = await HerzliyaCityRules().assess(session, opp.id)
    assert a["cap_400_sqm"] == 8000.0
    assert a["cap_400_certainty"] == Certainty.ESTIMATE.value
    assert a["cap_400_reliable"] is False            # ההחרגה שאחרי 2005 לא נבדקה
    assert not [c for c in a["checks"] if c["id"] == "existing_area"]


@pytest.mark.asyncio
async def test_the_cap_becomes_reliable_once_the_archive_answered(session):
    opp = await _opportunity(session, "9003", post_2005_permit=False, **ANSWERED)
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="existing_area", value=2000.0,
        certainty=Certainty.ESTIMATE.value, source_url="https://example.test/x",
        retrieved_at=datetime.now(timezone.utc), location="גוש 9003"))
    await session.flush()
    a = await HerzliyaCityRules().assess(session, opp.id)
    assert a["cap_400_reliable"] is True
    assert "לא נבדק" not in a["cap_400_basis"]


@pytest.mark.asyncio
async def test_a_stale_source_stops_deciding_and_says_so(session):
    """הגיל חוסם בשקט. ‏`stale_fields` קיימת כדי שזה לא יתגלה מול לקוח."""
    opp = await _opportunity(session, "9004", **{k: v for k, v in ANSWERED.items()
                                                 if k != "floors"})
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="floors", value=4,
        certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
        retrieved_at=datetime.now(timezone.utc) - timedelta(days=400),
        location="גוש 9004"))
    await session.flush()
    a = await HerzliyaCityRules().assess(session, opp.id)
    assert "floors" in a["stale_fields"]
    assert next(c["status"] for c in a["checks"] if c["id"] == "floors") == "unknown"


# ── הדגל שהלקוח רואה ──

def test_threshold_open_lists_only_the_gates_of_70a():
    checks = [{"id": "residential_share", "status": "unknown"},
              {"id": "permit_date", "status": "unknown"},
              {"id": "street_width", "status": "unknown"},      # לא שער סף
              {"id": "units", "status": "passed"}]
    assert _threshold_open(checks) == ["permit_date", "residential_share"]


@pytest.mark.asyncio
async def test_a_candidate_whose_threshold_was_never_asked_is_not_deliverable(session):
    """‏686 מ-699 דווחו כניתנים למסירה בעוד שהארכיון מעולם לא נמשך עבורם.
    ״נשאר במסלול״ ו״אפשר למסור״ הם שתי שאלות, והן התמזגו לדגל אחד."""
    no_archive = {k: v for k, v in ANSWERED.items()
                  if k not in ("permit_date", "strengthened", "occupied")}
    await _opportunity(session, "9005", **no_archive)
    counts = await refresh(session, HerzliyaCityRules(), "herzliya")
    assert counts  # הריצה כוללת את כל העיר; נבדוק את השורה עצמה
    opp = (await session.execute(
        __import__("sqlalchemy").select(Opportunity).where(Opportunity.block == "9005")
    )).scalar_one()
    a = opp.metadata_json["assessment"]
    assert a["screenable"] is True          # נשאר במסלול
    assert a["deliverable"] is False        # תנאי הסף לא נשאל
    assert "permit_date" in a["threshold_open"]


@pytest.mark.asyncio
async def test_the_unobtainable_gate_alone_does_not_block_delivery(session):
    """אין מקור פתוח לחלק המשמש למגורים. אילו הוא חסם — שום חלקה בעיר לא
    הייתה נמסרת לעולם, וזו אינה התשובה הנכונה אלא ויתור על המוצר."""
    await _opportunity(session, "9006", post_2005_permit=False, **ANSWERED)
    await refresh(session, HerzliyaCityRules(), "herzliya")
    opp = (await session.execute(
        __import__("sqlalchemy").select(Opportunity).where(Opportunity.block == "9006")
    )).scalar_one()
    a = opp.metadata_json["assessment"]
    assert a["threshold_open"] == ["residential_share"]
    assert a["deliverable"] is True
    assert a["status"] in DELIVERABLE
