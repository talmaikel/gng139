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
    assert "residential_share" in {g["id"] for g in gaps["unobtainable"]}
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
    # ההזדמנות האמיתית ולא אובייקט מנותק: מאז חיבור B1 ו-B3 הפונקציה
    # קוראת גם לוח דירות והערכת שווי, וזה חלק מההתנהגות שנבדקת כאן.
    bare = await _economics(session, opp, {"cap_400_sqm": None}, {})
    assert bare["scenario"] is None and bare["is_deliverable"] is False
    assert "DOS-03" in bare["why"]
    assert d["economics"]["assumptions"]


@pytest.mark.asyncio
async def test_the_scenario_says_it_is_not_a_signed_appraisal(session):
    c, _, opp = await _delivered(session)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert "שמאי" in d["economics"]["disclaimer"]
    # ‏**השתנה ב-14.09 בהחלטת בועז.** היעדר שומת השבחה כבר אינו חוסם:
    # במקומה מוצג הסף, שהוא אמירה שלמה ולא חוסר. מה שלא השתנה —
    # התיק אומר במפורש שאינו דוח שמאי חתום.
    assert "betterment_base_ils" not in d["economics"]["inputs_missing"]
    assert d["economics"]["betterment"]["breakeven_ils"] is not None \
        or d["economics"]["betterment"]["category"] == "no_threshold"


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
    unobtainable = {x["id"] for x in g["unobtainable"]}
    never_asked = {x["id"] for x in g["never_asked"]}
    assert "residential_share" in unobtainable
    assert "residential_share" not in never_asked
    assert not never_asked & unobtainable
    # והתווית בעברית נוסעת יחד עם המזהה, כדי שה-PDF לא ידפיס שם שדה
    assert all(x["label"] and not x["label"].isascii() for x in g["unobtainable"])


# ── חיבור B1 ו-B3 לתיק שהלקוח רואה ──
#
# שתי עבודות נבנו אל מסלול ה-worker, והתיק שהמסך מציג המשיך לקרוא
# ‏45,000 ₪/מ״ר ו-70 מ״ר מספריית ההנחות. הבדיקות כאן הן מה שמונע מהתפר
# הזה להיפתח שוב: הן נופלות אם התיק יחזור להתעלם מהנתון לחלקה.

@pytest.mark.asyncio
async def test_without_a_valuation_the_price_is_the_city_wide_estimate(session):
    c, _, opp = await _delivered(session, block="9640")
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    price = d["economics"]["live_inputs"]["sale_price"]
    assert price["resolved"] is False
    assert price["certainty"] == "estimate"
    assert "אומדן אחיד לעיר" in price["label"]


@pytest.mark.asyncio
async def test_a_stored_valuation_replaces_the_city_wide_estimate(session):
    from datetime import date, datetime, timezone

    from app.services.market_data.repository import add_valuation_run
    from app.services.market_data.schemas import MarketValuation, ValuationStatus

    c, _, opp = await _delivered(session, block="9641")
    add_valuation_run(
        session, opportunity_id=opp.id,
        valuation=MarketValuation(
            status=ValuationStatus.ESTIMATED, as_of_date=date(2026, 9, 1),
            fetched_at=datetime.now(timezone.utc), lookback_months=12, radius_m=500,
            comparable_count=17, comparable_sales=[], room_estimates=[],
            blended_price_per_sqm_ils=52_300.0, is_unit_mix_adjusted=True),
        parameters={"unit_mix_state": "x", "targets": []})
    await session.flush()

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    price = d["economics"]["live_inputs"]["sale_price"]
    assert price["resolved"] is True
    assert price["value"] == 52_300.0
    from app.evidence import DECIDING
    assert price["certainty"] in DECIDING
    assert "17 עסקאות" in price["label"]
    # והמחיר באמת נכנס לחישוב, ולא רק לתצוגה
    assert d["economics"]["scenario"]["total_revenue_ils"] > 0


@pytest.mark.asyncio
async def test_a_verified_complete_schedule_stops_blocking_delivery(session):
    """‏**החוסם יורד רק כשהלוח מכסה את כל הבניין.**

    ‏`may_decide` של B3 דורש ודאות מכריעה, לוח שלם, ובלי סתירה מול
    הספירה העירונית. התיק מכבד אותו ואינו שופט בעצמו.
    """
    from app.models.dwelling_unit import DwellingUnit

    c, _, opp = await _delivered(session, block="9642")
    assert opp.existing_units, "הבדיקה נשענת על ספירה עירונית קיימת"
    for i in range(opp.existing_units):
        session.add(DwellingUnit(
            opportunity_id=opp.id, source_key=f"permit#unit{i}", unit_label=str(i + 1),
            area_sqm=64.0 + i, certainty=Certainty.MANUALLY_VERIFIED,
            requires_human_review=False, method="manual"))
    await session.flush()

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    unit = d["economics"]["live_inputs"]["unit_area"]
    assert unit["resolved"] is True
    assert unit["per_unit_detail_available"] is True
    assert "אומת ידנית" in unit["label"]
    assert "average_existing_unit_sqm" not in d["economics"]["inputs_missing"]
    # ‏`resolved` עדיין מבחין בין מאושר לנקרא, גם כששניהם אינם חוסמים.
    assert d["economics"]["scenario"] is not None


@pytest.mark.asyncio
async def test_a_partial_schedule_is_shown_and_marked_unverified(session):
    """לוח מאושר שמכסה דירה אחת מתוך רבות מדווח, ומסומן כלא-מכריע.

    ‏**החסימה ירדה ב-14.09 בהחלטת בועז**, כי הכלל ״רק מאושר מכריע״
    הפך את השדה לבלתי-פתיר בייצור — אין מסך שבו אדם מאשר. הסימון
    נשאר: ‏`resolved=False`, והתווית אומרת מאיפה המספר הגיע.
    """
    from app.models.dwelling_unit import DwellingUnit

    c, _, opp = await _delivered(session, block="9643")
    session.add(DwellingUnit(
        opportunity_id=opp.id, source_key="permit#unit1", unit_label="1",
        area_sqm=64.0, certainty=Certainty.MANUALLY_VERIFIED,
        requires_human_review=False, method="manual"))
    await session.flush()

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    unit = d["economics"]["live_inputs"]["unit_area"]
    assert unit["value"] == 64.0                     # מוצג
    assert unit["resolved"] is False                 # ומסומן כלא-מכריע
    assert "average_existing_unit_sqm" not in d["economics"]["inputs_missing"]
    assert "לוח דירות" in unit["label"]              # והתווית אומרת מאיפה


@pytest.mark.asyncio
async def test_a_valuation_without_an_explicit_unit_mix_does_not_decide(session):
    """‏**הגייט של חן, מ-PR #12.**

    ‏B1 מחשב מחיר משוקלל *מתוך* תמהיל דירות. הערכה שלא הותאמה לתמהיל
    מפורש נושאת משקלים שנגזרו מהנחה — ולהציג אותה כמחיר מעסקאות זה
    לייבא הנחה בשקט. הגרסה הראשונה שלי לא בדקה את זה.
    """
    from datetime import date, datetime, timezone

    from app.services.market_data.repository import add_valuation_run
    from app.services.market_data.schemas import MarketValuation, ValuationStatus

    c, _, opp = await _delivered(session, block="9644")
    add_valuation_run(
        session, opportunity_id=opp.id,
        valuation=MarketValuation(
            status=ValuationStatus.ESTIMATED, as_of_date=date(2026, 9, 1),
            fetched_at=datetime.now(timezone.utc), lookback_months=12, radius_m=500,
            comparable_count=9, comparable_sales=[], room_estimates=[],
            blended_price_per_sqm_ils=61_000.0, is_unit_mix_adjusted=False),
        parameters={"unit_mix_state": "inferred", "targets": []})
    await session.flush()

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    price = d["economics"]["live_inputs"]["sale_price"]
    assert price["resolved"] is False
    assert price["value"] != 61_000.0            # לא הוכרע
    assert price["valuation_present"] is True    # אבל כן נחשף
    assert price["comparable_count"] == 9
    assert "תמהיל" in price["label"]


# ── B11 · סף ההשבחה ──

@pytest.mark.asyncio
async def test_the_dossier_says_how_much_betterment_the_project_survives(session):
    """לא מעריכים את ההשבחה — מחשבים עד היכן היא נספגת, ומתרגמים
    את זה לשווי מ״ר זכויות, שהוא המספר שיזם שופט."""
    c, _, opp = await _delivered(session, block="9645")
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    b = d["economics"]["betterment"]

    assert b["rate"] == 0.25                         # §19(ב)(10א)
    assert b["category"] in {"no_threshold", "resilient", "marginal"}
    assert "שומה" in b["note"]                       # נאמר במפורש שזו אינה שומה
    # והסף אומר על מה הוא עדיין נשען ולא מוצג כנחרץ
    assert "שטח דירה קיימת ממוצע" in b["rests_on_unresolved_inputs"]

    if b["breakeven_ils"] is not None:
        assert b["breakeven_ils"] > 0
        assert b["breakeven_per_added_sqm_ils"] > 0
    else:
        # ״אין סף״ הוא ממצא ולא כישלון: אין שיעור השבחה שמציל את החלקה
        assert b["category"] == "no_threshold"
        assert "אינה ההיטל" in b["category_label"]


def test_the_breakeven_is_solved_numerically_and_not_by_the_formula():
    """‏`profit(0) / rate` נראה נכון ושוגה בכ-1.5%, כי ההיטל גורר
    עלויות נגזרות. הבדיקה מוודאת שהסף באמת מאפס את הרווח."""
    from app.services.economic.betterment import breakeven_betterment

    # רווח לינארי בהיטל, פלוס גרירה של 5% על ההיטל עצמו
    def profit(base):
        return 60_000_000 - 0.25 * base * 1.05

    rate = 0.25
    be = breakeven_betterment(profit, rate=rate)
    assert be is not None
    assert abs(profit(be)) < 1.0                     # מאפס בפועל
    assert abs(be - 60_000_000 / rate) > 1_000_000   # והנוסחה הייתה שוגה


def test_a_project_that_loses_money_at_zero_betterment_has_no_threshold():
    from app.services.economic.betterment import breakeven_betterment

    assert breakeven_betterment(lambda _b: -5_000_000, rate=0.25) is None


def test_the_reference_calculation_from_a_developer_is_reproduced_exactly():
    """חישוב ההתייחסות שהתקבל מחברה יזמית. **שני המספרים אינם מחירי
    דירות:** ‏26,000 הוא שווי הנכס כפי שהוא לכל מ״ר בנוי, ו-12,000 הוא
    רכיב הקרקע לכל מ״ר זכויות — לפני שבונים עליו."""
    from app.services.economic.betterment import REFERENCE, betterment_from_land_values

    r = REFERENCE
    e = betterment_from_land_values(
        existing_area_sqm=r["existing_area_sqm"],
        existing_value_per_sqm_ils=r["existing_value_per_sqm_ils"],
        new_rights_sqm=r["new_rights_sqm"],
        land_value_per_right_ils=r["land_value_per_right_ils"])
    assert e.betterment_ils == pytest.approx(r["betterment_ils"], abs=1)
    assert e.levy(0.25) == pytest.approx(r["levy_ils"], abs=1)


def test_the_developer_method_is_numerically_fragile_and_says_so():
    """הממצא המרכזי על השיטה: הפרש בין שני מספרים גדולים. ‏10% במקדם
    אחד מזיזים את ההיטל ב-47%."""
    from app.services.economic.betterment import (
        REFERENCE, betterment_from_land_values, sensitivity,
    )

    r = REFERENCE
    def levy(existing_value, land_value):
        return betterment_from_land_values(
            existing_area_sqm=r["existing_area_sqm"],
            existing_value_per_sqm_ils=existing_value,
            new_rights_sqm=r["new_rights_sqm"],
            land_value_per_right_ils=land_value).levy(0.25)

    s = sensitivity(levy, r["existing_value_per_sqm_ils"], r["land_value_per_right_ils"])
    swing = abs(s["land_value_up_ils"] / s["base_ils"] - 1)
    assert swing > 0.40, "‏10% בשווי מ״ר זכויות חייבים להזיז את ההיטל בהרבה"


@pytest.mark.asyncio
async def test_the_levy_estimate_needs_prices_of_existing_flats_not_new_ones(session):
    """‏**מחיר דירה חדשה ומחיר דירה קיימת אינם אותו מספר.**

    ההכנסות מחושבות לפי מחיר דירה חדשה. שווי המצב הקיים — הצד ה״לפני״
    של ההשבחה — הוא מחיר דירה **קיימת**, והוא נמוך משמעותית. השוואת
    השניים באותו מספר הראתה ״אין השבחה״ בכל תשע החלקות.

    עסקאות ההשוואה של B1 הן בדירות קיימות, ולכן הן המקור הנכון —
    ובלעדיהן אין אומדן, יש רק סף.
    """
    from datetime import date, datetime, timezone

    from app.services.market_data.repository import add_valuation_run
    from app.services.market_data.schemas import MarketValuation, ValuationStatus

    c, _, opp = await _delivered(session, block="9646")

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    b = d["economics"]["betterment"]
    assert d["economics"]["live_inputs"]["existing_price"]["resolved"] is False
    assert b["estimate"] is None                     # אין עסקאות → אין אומדן
    assert "אין אומדן" in d["economics"]["live_inputs"]["existing_price"]["label"]

    add_valuation_run(
        session, opportunity_id=opp.id,
        valuation=MarketValuation(
            status=ValuationStatus.ESTIMATED, as_of_date=date(2026, 9, 1),
            fetched_at=datetime.now(timezone.utc), lookback_months=12, radius_m=500,
            comparable_count=23, comparable_sales=[], room_estimates=[],
            blended_price_per_sqm_ils=26_000.0, is_unit_mix_adjusted=True),
        parameters={"unit_mix_state": "explicit", "targets": []})
    await session.flush()

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    b = d["economics"]["betterment"]
    assert d["economics"]["live_inputs"]["existing_price"]["value"] == 26_000.0

    # ‏**ועדיין אין אומדן — וזו המסקנה.** אותה הערכה מזינה גם את
    # ההכנסות (מחיר דירה חדשה) וגם את הצד ה״לפני״ (מחיר דירה קיימת).
    # עסקאות GovMap אינן מסוננות לחדש מול יד שנייה, וכשאותו מספר עומד
    # בשני הצדדים — ״אין השבחה״ בכל חלקה. הסף אינו תלוי בכך.
    assert b["estimate"] is None
    assert "אינם מופרדים" in b["estimate_withheld_because"]
    assert b["levy"]["viable_up_to_ils"] is not None or b["category"] == "no_threshold"


@pytest.mark.asyncio
async def test_the_levy_is_given_as_a_range_and_a_ceiling(session):
    """היזם מקבל שני מספרים: כמה צפוי, ועד כמה נסבל."""
    c, _, opp = await _delivered(session, block="9647")
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    levy = d["economics"]["betterment"]["levy"]

    assert levy["rate"] == 0.25
    if levy["viable_up_to_ils"] is not None:
        assert levy["viable_up_to_ils"] > 0
    if levy["estimate_ils"] is not None:
        assert levy["low_ils"] <= levy["estimate_ils"] <= levy["high_ils"]


def test_the_residual_land_value_is_what_the_developer_can_pay():
    """‏12,000 בגיליון היזמי הוא הנחה. כאן הוא נגזר: מה שנשאר מההכנסות
    אחרי כל העלויות ואחרי הרווח הנדרש."""
    from app.services.economic.betterment import residual_land_value

    land = residual_land_value(
        total_revenue_ils=100e6, total_cost_ils=80e6, land_cost_ils=30e6,
        finance_ratio=0.05, developer_profit_target_ratio=0.20)
    # בדיקת ההיפוך: עם הקרקע הזו, ההכנסות הן בדיוק עלות ועוד רווח היעד
    cost = ((80e6 / 1.05 - 30e6) + land) * 1.05
    assert cost == pytest.approx(100e6 / 1.20, rel=1e-9)


@pytest.mark.asyncio
async def test_the_dossier_prices_parking_from_the_appraisers_survey(session):
    """התיק שהלקוח רואה משתמש ב-3,900 ₪ ולא ב-6,000 שבספרייה."""
    c, _, opp = await _delivered(session, block="9648")
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    ug = d["economics"]["assumptions"]["underground_cost_per_sqm_ils"]
    assert ug["value"] == 3_900.0
    assert ug["status"] == "data"
    assert "שמאי" in ug["source"]
