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


def test_an_estimate_that_implies_a_thousand_metres_per_flat_is_withheld():
    """‏`gross` הוא טביעת הרגל הכוללת כפול **מקסימום** הקומות בחלקה, ולכן
    מבנה נמוך לצד גבוה מוכפל גם הוא בגובה הגבוה. הנדיב 3: 7 דירות, מגרש
    2,303 מ״ר, ותקרת 400% של 30,632 מ״ר.

    אי אפשר לתקן את האומדן מכאן — אפשר לזהות שהוא שבור ולא לכתוב אותו.
    ״לא ידוע״ עדיף על 30,632."""
    sources = _load("source_fetched.json")

    def area(gross, apt):
        rows = {r["field"]: r for r in
                _rows("x/1", {**SURV, "gross": gross, "apt": apt}, {}, {}, sources, [])}
        return rows["existing_area"]["value"]

    assert area(2000, 28) is not None          # 48 מ"ר לדירה — סביר
    assert area(11447, 7) is None              # 1,094 מ"ר לדירה — שבור


def test_a_plot_with_no_unit_count_still_gets_its_area_estimate():
    """הסינון הוא על **היחס**. בלי מספר דירות אין יחס, ואין מה לפסול."""
    sources = _load("source_fetched.json")
    rows = {r["field"]: r for r in
            _rows("x/1", {**SURV, "apt": 999, "gross": 11447}, {}, {}, sources, [])}
    assert rows["existing_area"]["value"] is not None
