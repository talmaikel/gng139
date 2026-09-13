"""התיק — ‏DOS-02, ‏DOS-03, ‏DOS-04 ו-ACC-08.

‏`assess()` חישב שרשרת מלאה מהיום הראשון, ושום נתיב לא החזיר אותה.
הבדיקות כאן על המבנה שהלקוח מקבל, ובעיקר על מה שאסור שייעלם ממנו.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.cities.herzliya import rights
from app.cities.herzliya.dossier import NotEntitled, TEMPLATE_VERSION, build
from app.cities.herzliya.rules import HerzliyaCityRules
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel
from app.models.package import Balance
from app.models.tenant import Company, User
from app.services.deliveries import deliver

SQUARE = ("MULTIPOLYGON(((34.8460000 32.1660000,34.8464000 32.1660000,"
          "34.8464000 32.1663000,34.8460000 32.1663000,34.8460000 32.1660000)))")

READY = dict(residential_zoning=True, permit_date="1978-01-01", strengthened=False,
             occupied=False, post_2005_permit=False, floors=4, units=28,
             scope_buildings=1, street_width=12.0,
             renewal_policy_category="התחדשות מגרשית מוטת מגורים",
             in_tama70=True, registration_area='שז"ר')


async def _company(session, name="חברת תיק"):
    c = Company(name=name, slug=f"k-{uuid.uuid4().hex[:8]}")
    session.add(c)
    await session.flush()
    session.add(Balance(company_id=c.id, credits_remaining=3))
    u = User(email=f"{uuid.uuid4().hex[:8]}@k.local", hashed_password="x", is_active=True,
             is_superuser=False, is_verified=True, full_name="בודק", role="member",
             company_id=c.id)
    session.add(u)
    await session.flush()
    return c, u


async def _opportunity(session, block, **fields):
    opp = Opportunity(city_code="herzliya", address=f"רחוב התיק {block}", block=block,
                      block_suffix=0, parcel="1", geom=f"SRID=4326;{SQUARE}",
                      area_sqm=1800.0, existing_units=28,
                      verification_level=VerificationLevel.RAW.value, metadata_json={})
    session.add(opp)
    await session.flush()
    now = datetime.now(timezone.utc)
    for field, value in fields.items():
        session.add(FieldEvidence(
            opportunity_id=opp.id, field=field, value=value,
            certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
            retrieved_at=now - timedelta(days=1), location=f"גוש {block} חלקה 1"))
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="existing_area", value=2000.0,
        certainty=Certainty.ESTIMATE.value, source_url="https://example.test/x",
        retrieved_at=now, location=f"גוש {block}", method="טביעת רגל × קומות × k"))
    await session.flush()
    return opp


async def _delivered(session, block="9601"):
    c, u = await _company(session)
    opp = await _opportunity(session, block, **READY)
    from app.cities.herzliya.assessments import refresh_one
    await refresh_one(session, HerzliyaCityRules(), opp.id)
    await deliver(session, opp.id, c.id, u.id,
                  rules_version="herzliya-policy-2026-02", data_version="2026-09-13")
    return c, u, opp


# ── ACC-08 · רק למי שקיבל ──

@pytest.mark.asyncio
async def test_a_company_without_a_delivery_cannot_read_the_dossier(session):
    """*״בקשה של חברה ללא הרשאה לתיק נדחית גם כשמזהה התיק ידוע״*."""
    c, u, opp = await _delivered(session)
    other, _ = await _company(session, "חברה אחרת")
    with pytest.raises(NotEntitled):
        await build(session, HerzliyaCityRules(), opp.id, other.id)
    # ולמי שקיבל — כן
    assert await build(session, HerzliyaCityRules(), opp.id, c.id)


@pytest.mark.asyncio
async def test_an_unknown_id_looks_the_same_as_one_without_permission(session):
    """‏404 ולא 403 בשתי הדרכים — אחרת המזהה הקיים מזוהה בהבדל בין השגיאות."""
    c, _ = await _company(session)
    with pytest.raises(NotEntitled):
        await build(session, HerzliyaCityRules(), uuid.uuid4(), c.id)


# ── DOS-02 · מה חייב להיות בתיק ──

@pytest.mark.asyncio
async def test_the_dossier_carries_the_whole_rights_chain_and_not_a_summary(session):
    """זה החלק שלא נחשף באף נתיב, והוא מה שהלקוח קונה."""
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    checks = d["rights"]["checks"]
    assert len(checks) >= 8
    assert {"residential_zoning", "permit_date", "floors", "units"} <= {c_["id"] for c_ in checks}
    # מקור וציטוט עמוד לכל שער — בלעדיהם אי אפשר לבדוק אותנו
    assert all(c_["source_url"] for c_ in checks)
    # לכל שער של §70א יש סעיף לצטט. `occupied` אינו בהם — הוא שער זמינות
    # מסחרית, ואין בחוק סעיף שאפשר להפנות אליו.
    assert all(c_.get("page") for c_ in checks if c_["id"] in rights.SECTION_70A_IDS)
    assert next(c_ for c_ in checks if c_["id"] == "occupied")["page"] is None
    for key in ("floors", "cap_400_sqm", "unit_mix", "parking"):
        assert key in d["rights"], key


@pytest.mark.asyncio
async def test_every_material_field_shows_its_source_date_and_certainty(session):
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert d["evidence"]
    for row in d["evidence"]:
        assert row["source_url"] and row["retrieved_at"] and row["location"], row["field"]
        assert row["certainty"] in {x.value for x in Certainty}


@pytest.mark.asyncio
async def test_an_estimate_is_marked_as_one_and_does_not_decide(session):
    """שטח קיים הוא אומדן, והוא מזין את תקרת 400%. התיק אומר את שניהם."""
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    area = next(r for r in d["evidence"] if r["field"] == "existing_area")
    assert area["certainty"] == Certainty.ESTIMATE.value
    assert area["decides"] is False
    assert d["economics"]["buildable_certainty"] == Certainty.ESTIMATE.value


# ── DOS-03 · חסר נשאר חסר ──

@pytest.mark.asyncio
async def test_the_gaps_section_is_a_chapter_and_not_a_footnote(session):
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    gaps = d["gaps"]
    # מבחן ה-70% אין לו מקור פתוח, והתיק מפריד בין ״לא נבדק״ ל״אין מקור״
    assert "residential_share" in gaps["unobtainable"]
    assert "residential_share" in {g["id"] for g in gaps["unknown_gates"]}
    assert "ארכיון מלא" in gaps["note"]


@pytest.mark.asyncio
async def test_a_missing_value_is_never_reported_as_zero(session):
    """‏DOS-03: *״אין להפוך נתון חסר לאפס״*."""
    c, u = await _company(session)
    opp = await _opportunity(session, "9602", **{k: v for k, v in READY.items()
                                                 if k != "street_width"})
    from app.cities.herzliya.assessments import refresh_one
    await refresh_one(session, HerzliyaCityRules(), opp.id)
    opp.metadata_json = {**opp.metadata_json,
                         "assessment": {**opp.metadata_json["assessment"], "deliverable": True}}
    await session.flush()
    await deliver(session, opp.id, c.id, u.id)

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert d["rights"]["floors"]["low"] is None          # ולא 0
    assert d["rights"]["floors"]["high"] is None
    # תקרת ה-400% כן קיימת — היא נגזרת מהשטח הקיים ולא מרוחב הרחוב — ולכן
    # התרחיש מחושב. מה שחסר הוא הקומות, והוא נשאר None ולא הופך לאפס.
    assert d["economics"]["scenario"] is not None


@pytest.mark.asyncio
async def test_an_economic_scenario_without_a_rights_ceiling_is_not_invented(session):
    c, u = await _company(session)
    opp = await _opportunity(session, "9603", **READY)
    opp.metadata_json = {"assessment": {"deliverable": True, "cap_400_sqm": None,
                                        "threshold_open": [], "screenable": True}}
    await session.flush()
    await deliver(session, opp.id, c.id, u.id)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    # ההערכה מחושבת מחדש בבנייה, ולכן התקרה כן קיימת — הבדיקה על ההתנהגות
    # כשאין: התרחיש יוצא None ולא אפסים.
    from app.cities.herzliya.dossier import _economics
    bare = _economics(Opportunity(city_code="herzliya", address="x", area_sqm=None,
                                  existing_units=None), {"cap_400_sqm": None})
    assert bare["scenario"] is None and bare["is_deliverable"] is False
    assert "DOS-03" in bare["why"]
    assert d["economics"]["assumptions"]


@pytest.mark.asyncio
async def test_the_scenario_says_it_is_not_a_signed_appraisal(session):
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert "שמאי" in d["economics"]["disclaimer"]
    assert d["economics"]["is_deliverable"] is False      # הנחות MISSING חוסמות
    assert "betterment_levy_ratio" in d["economics"]["inputs_missing"]


# ── DOS-04 · גרסאות ──

@pytest.mark.asyncio
async def test_the_dossier_carries_all_three_versions(session):
    """*״התוצר כולל גרסת נתונים, כללים ותבנית״*."""
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert d["versions"] == {"rules_version": "herzliya-policy-2026-02",
                             "data_version": "2026-09-13",
                             "template_version": TEMPLATE_VERSION}


@pytest.mark.asyncio
async def test_a_gate_appears_in_one_gap_category_only(session):
    """שדה שאין לו מקור פתוח הופיע גם כ״מעולם לא נשאל״ — וזה קורא כמו
    רשלנות. הוא נשאל; אין ממי לקבל תשובה."""
    c, _, opp = await _delivered(session)
    g = (await build(session, HerzliyaCityRules(), opp.id, c.id))["gaps"]
    assert "residential_share" in g["unobtainable"]
    assert "residential_share" not in g["never_asked"]
    assert not set(g["never_asked"]) & set(g["unobtainable"])
