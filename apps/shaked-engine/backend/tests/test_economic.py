"""התסריט הכלכלי — ECO-01 עד ECO-03.

המודול הזה מפיק את המספר היחיד שאדם יקבל לפיו החלטה, והוא היה ללא בדיקה
אחת. שלוש מהבדיקות כאן נכתבו כדי לתפוס באג שכבר היה שם, ולא כדי לאשר
התנהגות קיימת.
"""
import pytest
from pydantic import ValidationError

from app.services.economic.assumptions import (
    Assumption, AssumptionStatus, get_assumptions)
from app.services.economic.calculator import calculate_feasibility as calc
from app.services.economic.schemas import FeasibilityInput as FI

# מועמד טיפוסי במלאי: 952 מ״ר מגרש, 7 דירות, תקרת 400% = 3,396 מ״ר
BASE = dict(plot_area_sqm=952.0, existing_units=7, buildable_area_sqm=3396.0,
            sale_price_per_sqm=45_000.0, construction_cost_per_sqm=8_000.0)


# ── ECO-01 · החישוב ──

def test_profit_is_measured_against_cost_and_not_against_revenue():
    """‏PRD 6.4: ״שיעור רווח על העלות הוא ההפרש חלקי ההוצאות״. על ההכנסות
    היה נותן מספר קטן יותר לאותו פרויקט, ושתי התעשיות משתמשות בשניהם."""
    r = calc(FI(**BASE))
    assert r.profit_margin_on_cost_ratio == pytest.approx(
        r.projected_profit_ils / r.total_cost_ils, abs=5e-5)   # התוצאה מעוגלת ל-4
    assert r.profit_margin_on_cost_ratio != pytest.approx(
        r.projected_profit_ils / r.total_revenue_ils, abs=5e-5)


def test_construction_is_paid_on_the_whole_building_and_sold_on_the_developers_share():
    """היזם בונה גם את דירות הדיירים ואינו מוכר אותן. חישוב עלות על חלקו
    בלבד היה מנפח את הרווח בשיעור של דירות הדיירים."""
    r = calc(FI(**BASE))
    assert r.total_construction_cost_ils == 3396.0 * 8_000.0
    assert r.total_revenue_ils == r.developer_allocation_sqm * 45_000.0
    assert r.developer_allocation_sqm < 3396.0


def test_tenant_area_is_sized_off_the_old_building_not_the_new_one():
    """אם הפיצוי נגזר מהבניין החדש, הוא צורך אותו במלואו בהגדרה — לא משנה
    כמה בונים. הבדיקה נועלת את זה: הכפלת הבניין מכפילה את חלק היזם בלבד."""
    small = calc(FI(**BASE))
    big = calc(FI(**{**BASE, "buildable_area_sqm": 6792.0}))
    assert small.tenant_allocation_sqm == big.tenant_allocation_sqm
    assert big.developer_allocation_sqm == small.developer_allocation_sqm + 3396.0


def test_extra_compensation_comes_out_of_the_developers_share():
    plain = calc(FI(**BASE))
    plus12 = calc(FI(**BASE, tenant_compensation_sqm_per_existing_unit=12.0))
    assert plus12.tenant_allocation_sqm == plain.tenant_allocation_sqm + 7 * 12.0
    assert plus12.projected_profit_ils < plain.projected_profit_ils


def test_a_building_that_cannot_rehouse_its_own_tenants_says_so(session=None):
    """‏60 דיירים ב-3,396 מ״ר החזירו חלק יזם 0 והפסד של 40 מיליון — כמו כל
    פרויקט גרעוני אחר. שום שדה לא אמר שהשיכון-מחדש עצמו אינו נכנס."""
    impossible = calc(FI(**{**BASE, "existing_units": 60}))
    assert impossible.tenants_fit is False
    assert impossible.developer_allocation_sqm == 0.0
    assert calc(FI(**BASE)).tenants_fit is True


def test_the_target_is_compared_and_not_assumed():
    assert calc(FI(**BASE, developer_profit_target_ratio=0.20)).meets_developer_target
    assert not calc(FI(**BASE, developer_profit_target_ratio=50.0)).meets_developer_target


# ── ECO-02 · ״לעולם לא להציג אומדן כנתון מאומת״ ──

def test_the_average_existing_flat_is_declared_and_not_a_default():
    """‏12.6 מיליון ₪ מפרידים בין דירה ממוצעת של 55 מ״ר ל-95 מ״ר על מועמד
    טיפוסי. הערך ישב כברירת מחדל בסכימה, העובד לא העביר אותו, והתיק לא
    דיווח עליו — כלומר המספר הגדול ביותר בתסריט לא היה מוצהר בשום מקום."""
    a = get_assumptions("herzliya")
    assert isinstance(a.average_existing_unit_sqm, Assumption)
    assert a.average_existing_unit_sqm.status is AssumptionStatus.MISSING
    assert "גרמושקה" in (a.average_existing_unit_sqm.source or "")

    spread = (calc(FI(**BASE, average_existing_unit_sqm=55.0)).projected_profit_ils
              - calc(FI(**BASE, average_existing_unit_sqm=95.0)).projected_profit_ils)
    assert spread > 10_000_000


def test_a_missing_assumption_blocks_delivery_without_blocking_the_calculation():
    """‏MISSING הוגדר עם ההערה ״חייב לחסום תוצאה מוכנה, לא להתאפס״ — ואז
    שום הנחה לא נשאה אותו ושום קוד לא קרא אותו. תסריט על מציין מקום עדיין
    שימושי לחשיבה; הוא פשוט אינו נמסר."""
    a = get_assumptions("herzliya")
    assert a.blocking() == ["average_existing_unit_sqm"]
    r = calc(FI(**BASE), missing_inputs=a.blocking())
    assert r.projected_profit_ils > 0          # חושב
    assert r.is_deliverable is False           # ולא נמסר
    assert r.inputs_missing == ["average_existing_unit_sqm"]


def test_a_scenario_built_only_on_known_inputs_is_deliverable():
    assert calc(FI(**BASE)).is_deliverable is True


def test_the_assumptions_report_cannot_silently_drop_an_entry():
    """הדוח בעובד נכתב ביד והשמיט שתי הנחות. עכשיו הוא נגזר מהשדות."""
    a = get_assumptions("herzliya")
    reported = set(a.report())
    declared = {n for n in a.__dataclass_fields__
                if isinstance(getattr(a, n), Assumption)}
    assert reported == declared
    assert all({"value", "status", "unit"} <= set(v) for v in a.report().values())


def test_every_figure_in_the_library_is_marked_and_dated():
    a = get_assumptions("herzliya")
    assert a.version and a.effective_date
    assert all(x["status"] in {s.value for s in AssumptionStatus} for x in a.report().values())
    # אף אחת מהן אינה DATA היום, וזה נכון — אף אחת לא הגיעה משמאי.
    assert not any(x["status"] == "data" for x in a.report().values())


def test_an_unknown_city_raises_instead_of_falling_back_to_herzliya():
    with pytest.raises(ValueError, match="netanya"):
        get_assumptions("netanya")


# ── ECO-03 · קלט שאינו קביל ──

@pytest.mark.parametrize("bad", [
    {"buildable_area_sqm": 0.0},        # בניין ללא שטח
    {"plot_area_sqm": -1.0},
    {"sale_price_per_sqm": 0.0},
    {"existing_units": -1},
    {"soft_cost_ratio": -0.1},
    {"average_existing_unit_sqm": 0.0},
])
def test_impossible_inputs_are_refused_rather_than_computed(bad):
    with pytest.raises(ValidationError):
        FI(**{**BASE, **bad})


# ── מה שהמודל אינו כולל ──

def test_the_model_is_missing_cost_lines_and_the_margin_shows_it():
    """‏305% רווח על העלות. אף פרויקט התחדשות אינו נראה כך, והמספר אינו באג
    בחישוב אלא **חוסר בשורות עלות**: אין מימון לארבע שנים, אין שיווק, אין
    היטל השבחה, אין שכר דירה לדיירים בתקופת הבנייה, ואין מע״מ.

    הבדיקה נועלת את הפער כדי שיהיה גלוי בקוד: מרווח שחורג מכל טווח מסחרי
    סביר הוא הראיה שהמודל חלקי. **אין להציג אותו ללקוח** לפני שהשורות
    החסרות נוספו — וזו הסיבה ש-`is_deliverable` כבר False ממילא.
    """
    r = calc(FI(**BASE), missing_inputs=get_assumptions("herzliya").blocking())
    assert r.profit_margin_on_cost_ratio > 1.0      # מעל 100% — לא סביר מסחרית
    assert r.is_deliverable is False
