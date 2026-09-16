"""זריעת שכבה א׳: שהשדות נושאים מקור, ושה-category אינו נדרס.

הבדיקה השנייה קיימת בגלל תקלה אמיתית: `metadata_json["category"]` הוא
קטגוריית הסינון של ה-engine, ובזריעה הראשונה נכתבה לשם קטגוריית מפת
המדיניות. כל 699 השורות נעלמו מ-`screen_herzliya_candidates` **בלי שגיאה**,
כי הן פשוט לא ענו על הפילטר. זה נראה כמו בסיס נתונים ריק.
"""
import pytest

from app.cities.herzliya.seed_layer_a import CATEGORY, _metadata, _rows, _load
from app.cities.herzliya.xplan_schema import QUEUE_ELIGIBLE_CATEGORIES
from app.evidence import Certainty

SURV = {"lot": 1816, "apt": 28, "floors": 4, "cat": "9", "entrances": 2, "pilotis": False}


def test_category_is_the_engines_screening_vocabulary_not_the_policy_map():
    m = _metadata("6537/222", SURV, {"width": 15.5})
    assert m["category"] in QUEUE_ELIGIBLE_CATEGORIES
    assert m["renewal_policy_category"] in CATEGORY.values()
    assert m["category"] != m["renewal_policy_category"]


def test_unmeasured_street_is_needs_verification_not_primary():
    assert _metadata("x/1", SURV, {})["category"] == "needs_verification"
    assert _metadata("x/1", SURV, {"width": 12.0})["category"] == "primary_candidate"


def test_every_evidence_row_carries_a_source_and_a_location():
    sources = _load("source_fetched.json")
    rows = _rows("6537/222", SURV, {"width": 15.5, "why": "x"}, {}, sources, [])
    assert rows
    for r in rows:
        assert r["source_url"].startswith("https://"), r["field"]
        assert r["retrieved_at"], r["field"]
        assert r["location"], r["field"]
        assert r["certainty"] in {c.value for c in Certainty}


def test_v2_width_is_verified_and_the_fallback_is_not():
    """רשומת frontages_v2: רוחב v2 מאומת. בלי רוחב v2 — נופלים לרוחב הקודם
    כדי שהחלקה לא תיעלם מהסינון, אבל מסומנת כלא מאומתת."""
    sources = _load("source_fetched.json")
    rows = lambda front: {r["field"]: r for r in _rows("6537/222", SURV, front, {}, sources, [])}
    v2 = rows({"width": 10.4, "width_v1": 17.3, "why": "x", "narrow": []})
    assert v2["street_width"]["value"] == 10.4
    assert v2["street_width_verified"]["value"] is True
    assert "street_narrow_frontages" not in v2
    fb = rows({"width": None, "width_v1": 33.0, "why": "x",
               "narrow": [{"width": 7.3, "tag": "residential", "name": "אחד העם"}]})
    assert fb["street_width"]["value"] == 33.0
    assert fb["street_width_verified"]["value"] is False
    assert "לא מאומת" in fb["street_width"]["method"]
    assert fb["street_narrow_frontages"]["value"] == "7.3 מ׳ (אחד העם)"
    assert _metadata("x/1", SURV, {"width": None, "width_v1": 33.0})["category"] == "primary_candidate"


def test_a_field_without_a_known_source_is_not_written_at_all():
    """בלי מקור אי אפשר אפילו לטעון שחיפשנו, ולכן אין שורה — לא MISSING."""
    rows = _rows("6537/222", SURV, {"width": 15.5}, {}, {}, [])
    assert rows == []


def test_a_source_that_was_read_and_came_back_empty_is_written_as_missing():
    """״נבדק ולא נמצא״ ו״לא נשאל״ נראו אותו דבר — שניהם היעדר שורה. התיק
    נקרא כאילו איש לא בדק, והדוקסטרינג של הקובץ טען שנכתב MISSING בעוד
    ששום שורה כזו לא נוצרה מעולם."""
    sources = _load("source_fetched.json")
    rows = {r["field"]: r for r in
            _rows("x/1", {"lot": 1816, "apt": 28, "cat": "9"}, {}, {}, sources, [])}
    assert rows["floors"]["certainty"] == Certainty.MISSING.value
    assert rows["floors"]["value"] is None
    assert rows["floors"]["source_url"] and rows["floors"]["location"]
    # וערך שנמצא אינו הופך ל-MISSING
    assert rows["parcel_area"]["certainty"] == Certainty.OFFICIAL.value


def test_a_missing_row_can_never_decide_a_gate():
    """‏MISSING אינו ב-DECIDING. אם היה — שדה ריק היה מכריע שער."""
    from app.evidence import DECIDING
    assert Certainty.MISSING.value not in DECIDING


def test_residential_zoning_is_seeded_as_the_first_gate_of_70a():
    sources = _load("source_fetched.json")
    rows = {r["field"]: r for r in
            _rows("x/1", SURV, {}, {"residential_zoning": True}, sources, [])}
    assert rows["residential_zoning"]["value"] is True
    assert rows["residential_zoning"]["certainty"] == Certainty.DERIVED.value


def test_a_permit_after_may_2005_is_recorded_for_the_cap_exclusion():
    """‏§70ב(א)(1)(ב). ‏False כאן פירושו ״נבדק בתיק ואין״, ולכן הוא ערך
    ולא היעדר — `cap_400` מבדיל בין השניים."""
    sources = _load("source_fetched.json")

    def flag(pdate):
        req = [dict(req=20060011, submitted="01/01/2006", action="תוספת בנייה",
                    permit="7", permit_date=pdate)]
        return {r["field"]: r for r in
                _rows("x/1", SURV, {}, {}, sources, req)}["post_2005_permit"]

    assert flag("19/05/2005")["value"] is True
    assert flag("18/05/2005")["value"] is False      # המועד עצמו אינו ״אחרי״
    # בקשה משנת 2006 שלא הופק לה היתר — התיק נקרא, ואין מה להחריג.
    assert flag("")["value"] is False
    assert flag("")["certainty"] == Certainty.DERIVED.value


def test_policy_categories_match_the_plans_wording():
    # עמ' 8 בהר/2323: שתיהן "מגרשית". "עירונית" אינו מופיע שם.
    assert all("מגרשית" in v for v in CATEGORY.values())


def test_the_permit_date_cites_the_archive_it_came_from():
    """מועד ההיתר נגזר משורות תיק הבניין. לצטט עליו את שכבת החלקות של
    GovMap פירושו ששעון ההתיישנות של השדה המכריע ביותר ב-§70א עוקב אחרי
    השליפה הלא נכונה, והקורא מופנה לשכבה שאין בה היתרים כלל."""
    sources = _load("source_fetched.json")
    archive = [dict(req=19780028, submitted="12/03/1978", action="פתיחת בקשה להיתר",
                    permit="1", permit_date="23/07/1978")]
    rows = {r["field"]: r for r in
            _rows("6537/222", SURV, {"width": 15.5}, {}, sources, archive)}
    for field in ("permit_date", "strengthened", "occupied"):
        assert "complot" in rows[field]["source_url"], field
        assert "govmap" not in rows[field]["source_url"], field


# ── קלטים שבורים שמנפחים את המספר הראשי ──

def test_the_999_sentinel_is_not_read_as_a_unit_count():
    """‏999 הוא ספירה שלא נעשתה. כערך אמיתי הוא מייצר 2,797 יחידות
    בתמהיל ו-999 חניות."""
    sources = _load("source_fetched.json")
    rows = {r["field"]: r for r in
            _rows("x/1", {**SURV, "apt": 999}, {}, {}, sources, [])}
    assert rows["units"]["certainty"] == Certainty.MISSING.value
    assert rows["units"]["value"] is None
    # ומספר אמיתי כן עובר
    ok = {r["field"]: r for r in _rows("x/1", {**SURV, "apt": 28}, {}, {}, sources, [])}
    assert ok["units"]["value"] == 28


def test_an_undercounted_unit_figure_is_withheld_and_the_measured_area_is_kept():
    """**שכבת נקודות הכתובת מחמיצה כניסות.** אלרואי דוד 32 — בניין בן 15
    קומות על 840 מ״ר טביעת רגל — רשום כארבע דירות; סביר שיש בו כ-84.

    השטח הבנוי נמדד מהגאומטריה ומהימן. מספר הדירות מגיע מנקודות כתובת
    שחלקן חסרות, והוא זה שנשבר — ולכן הוא זה שנפסל. הגרסה הראשונה פסלה
    את השדה ההפוך."""
    sources = _load("source_fetched.json")

    def row(field, gross, apt):
        rows = {r["field"]: r for r in
                _rows("x/1", {**SURV, "gross": gross, "apt": apt}, {}, {}, sources, [])}
        return rows[field]

    assert row("units", 2000, 28)["value"] == 28              # 48 מ"ר לדירה — סביר
    assert row("units", 11447, 7)["value"] is None            # 1,094 — ספירה שבורה
    # והשטח, שנמדד מהגאומטריה, נשאר
    assert row("existing_area", 11447, 7)["value"] is not None


def test_a_plot_without_a_unit_count_keeps_its_area():
    """הסינון הוא על **היחס**. בלי מספר דירות אין יחס, ואין מה לפסול."""
    sources = _load("source_fetched.json")
    rows = {r["field"]: r for r in
            _rows("x/1", {**SURV, "apt": 999, "gross": 11447}, {}, {}, sources, [])}
    assert rows["existing_area"]["value"] is not None
    assert rows["units"]["value"] is None


def test_a_broken_count_blocks_delivery_rather_than_scaling_a_wrong_mix():
    """לשער §70א(3) ספירה חסרה עדיין מספיקה — אבל אותו מספר מזין את
    התמהיל (×2.8), את החניה ואת פיצוי הדיירים, ושם הוא שגוי פי עשרה
    ומנפח את הרווח. תיק כזה אינו ניתן למסירה."""
    from app.cities.herzliya import rights
    assert "units" in rights.THRESHOLD_IDS
    assert rights.unit_mix(7)["units_max"] == 22        # מה שהיה נמסר
    assert rights.unit_mix(77)["units_max"] == 245      # מה שנכון


@pytest.mark.asyncio
async def test_reseeding_does_not_erase_a_building_file_fetched_on_demand(session):
    """שליפת תיק היא יקרה, מוגבלת בקצב, ומדיניות הסיכון מחייבת לשמור
    אותה **לתמיד**. הזריעה מחקה את כל ראיות ההזדמנות — וארבעה תיקים
    שנשלפו להדגמה נמחקו בזריעה שאחריה, בלי סימן."""
    from datetime import datetime, timezone

    from app.cities.herzliya.seed_layer_a import ARCHIVE_HOST, seed
    from app.models.evidence import FieldEvidence
    from app.models.opportunity import Opportunity
    from sqlalchemy import select

    # ‏**זריעה ראשונה, כי מסד נקי הוא המצב הנכון להניח.** הבדיקה הזו
    # קראה כאן `scalar_one()` על מסד שהיא לא זרעה, ולכן עברה רק על
    # מחשב שכבר יש בו נתונים. היא נפלה בהרצה הראשונה של ה-CI —
    # `NoResultFound` — וזה בדיוק מה ש-CI נועד לתפוס: בדיקה שתלויה
    # במצב מקומי אינה בודקת את הקוד אלא את המחשב שעליו היא רצה.
    await seed(limit=None)
    opp = (await session.execute(
        select(Opportunity).where(Opportunity.city_code == "herzliya").limit(1))).scalars().first()
    assert opp is not None, "הזריעה לא יצרה אף הזדמנות בהרצליה"
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="permit_date", value="1978-01-01",
        certainty=Certainty.DERIVED.value,
        source_url=f"https://handasi.{ARCHIVE_HOST}/magicscripts/mgrqispi.dll",
        retrieved_at=datetime.now(timezone.utc), location="תיק 475 · 6 בקשות",
        method="שורות הבקשות בתיק הבניין"))
    await session.flush()

    await seed(limit=None)

    kept = (await session.execute(
        select(FieldEvidence).where(FieldEvidence.opportunity_id == opp.id,
                                    FieldEvidence.source_url.like(f"%{ARCHIVE_HOST}%")
                                    ))).scalars().all()
    assert kept, "ראיית ארכיון שנשלפה לפי דרישה נמחקה בזריעה"


def test_the_rejected_count_does_not_survive_in_the_opportunity_column():
    """הראיה נחסמה, אבל העמודה המשיכה לשאת את המספר — והיא זו שמזינה את
    התחשיב הכלכלי בתיק ואת המיון במסך. דלת אחורית לאותו ערך בדיוק."""
    from app.cities.herzliya.seed_layer_a import usable_units
    assert usable_units({"apt": 28, "gross": 4000}) == 28
    assert usable_units({"apt": 999, "gross": 2910}) is None
    assert usable_units({"apt": 7, "gross": 11447}) is None      # 1,094 מ"ר לדירה
    # ‏#90 · מנופחת: גורדון א ד 7, ‏99 דירות על 827 מ"ר ברוטו — 5.6 מ"ר לדירה
    assert usable_units({"apt": 99, "gross": 827}) is None
    assert usable_units({"apt": 60, "gross": 1095}) is None      # הדר 42, 12 מ"ר
    assert usable_units({"apt": 29, "gross": 4223}) == 29        # אלוף יגאל אלון 40, 97 מ"ר


# ── שחזור תיקי הארכיון ──

def test_a_fetched_building_file_is_reproducible_from_the_repo():
    """שליפת תיק מוגבלת בקצב, והמדיניות מחייבת לשמור אותה **לתמיד** —
    אבל היא נכתבה למסד בלבד, כלומר חיה על מכונה אחת. מכונה חדשה שתזרע
    מאפס קיבלה 5 מועמדים מוכנים במקום 9, בלי הסבר."""
    from app.cities.herzliya.seed_layer_a import FETCHED_FILE, _fetched_rows

    fetched = _load(FETCHED_FILE)
    assert fetched, "קובץ התיקים שנשלפו ריק — ‏`--export` לא רץ"

    key = next(iter(fetched))
    rows = {r["field"]: r for r in _fetched_rows(key, fetched[key])}
    assert rows, f"{key} אינו מייצר שורות ראיה"
    for r in rows.values():
        assert r["source_url"] and r["retrieved_at"] and r["location"]
        assert r["certainty"] == Certainty.DERIVED.value


def test_the_export_carries_facts_only_and_never_the_page_itself():
    """‏DATA_LAW: עובדות נגזרות מותרות ללא הגבלה; ‏HTML גולמי נשמר פנימית
    עם TTL ואינו מוצג; שמות מבקשים אינם נקראים מלכתחילה. הקובץ הזה יושב
    **בגיט**, ולכן הגבול נאכף בבדיקה ולא בזיכרון."""
    from app.cities.herzliya.archive_facts import ARCHIVE_FIELDS
    from app.cities.herzliya.seed_layer_a import FETCHED_FILE

    for key, entry in _load(FETCHED_FILE).items():
        assert set(entry) <= {"fields", "source_url", "location", "method", "retrieved_at"}, key
        assert set(entry["fields"]) <= set(ARCHIVE_FIELDS), key
        # לא HTML, ולא שורות בקשה עם עמודת שם
        assert "html" not in entry and "requests" not in entry, key


def test_an_entry_without_provenance_is_not_written_at_all():
    """אותו כלל כמו בכל ראיה: בלי מקור, מיקום ומועד — אין שורה."""
    from app.cities.herzliya.seed_layer_a import _fetched_rows

    full = {"fields": {"permit_date": "1978-01-01"}, "source_url": "https://x.test/a",
            "location": "גוש 1 חלקה 1", "retrieved_at": "2026-09-13T10:00:00+00:00"}
    assert _fetched_rows("1/1", full)
    for missing in ("source_url", "location", "retrieved_at"):
        assert _fetched_rows("1/1", {**full, missing: None}) == []
    assert _fetched_rows("1/1", None) == []
