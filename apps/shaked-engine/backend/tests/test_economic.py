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
from app.services.economic.construction_costs import resolve_construction_cost_per_sqm
from app.services.economic.schemas import FeasibilityInput as FI

# מועמד טיפוסי במלאי: 952 מ״ר מגרש, 7 דירות, תקרת 400% = 3,396 מ״ר.
# המחירים נלקחים מספריית ההנחות ולא נכתבים כאן שוב — שני מקורות אמת היו
# מאפשרים לספרייה להתעדכן בעוד הבדיקות ממשיכות לאשר את הערכים הישנים.
_A = get_assumptions("herzliya")
# עלות הבנייה **אינה** נלקחת מ-`_A.construction_cost_per_sqm_ils` — השדה הזה
# הוא כיום מציין מקום בלבד (B2). מה שהתסריט האמיתי משתמש בו הוא התוצאה של
# `resolve_construction_cost_per_sqm`, בדיוק כפי ש-worker.py קורא לה.
_CONSTRUCTION_COST_PER_SQM = resolve_construction_cost_per_sqm(
    "herzliya", developer_value=None).value_ils_per_sqm
BASE = dict(plot_area_sqm=952.0, existing_units=7, buildable_area_sqm=3396.0,
            sale_price_per_sqm=_A.sale_price_per_sqm_ils.value,
            construction_cost_per_sqm=_CONSTRUCTION_COST_PER_SQM)


# ── ECO-01 · החישוב ──

def test_profit_is_measured_against_cost_and_not_against_revenue():
    """‏PRD 6.4: ״שיעור רווח על העלות הוא ההפרש חלקי ההוצאות״. על ההכנסות
    היה נותן מספר קטן יותר לאותו פרויקט, ושתי התעשיות משתמשות בשניהם."""
    r = calc(FI(**BASE))
    assert r.profit_margin_on_cost_ratio == pytest.approx(
        r.projected_profit_ils / r.total_cost_ils, abs=5e-5)   # התוצאה מעוגלת ל-4
    assert r.profit_margin_on_cost_ratio != pytest.approx(
        r.projected_profit_ils / r.total_revenue_ils, abs=5e-5)


def test_construction_is_paid_on_everything_built_and_sold_on_main_area_only():
    """תקרת ה-400% כוללת שטחי שירות וממ״ד — נבנים, לא נמכרים במחיר דירה.
    והחניון התת-קרקעי אינו נספר בתקרה כלל אבל כן משולם."""
    r = calc(FI(**BASE))
    assert r.total_construction_cost_ils == 3396.0 * _CONSTRUCTION_COST_PER_SQM
    assert r.constructed_area_sqm == 3396.0 * 1.40                # ועוד חניון
    assert r.total_underground_cost_ils > 0
    assert r.sellable_main_sqm == pytest.approx(3396.0 * 0.78)    # ורק זה נמכר
    assert r.sellable_main_sqm < 3396.0


def test_service_area_is_not_sold_at_apartment_prices():
    """הגרסה הקודמת מכרה ממ״ד, מחסן וחדר מדרגות ב-45,000 ₪ למ״ר."""
    full = calc(FI(**{**BASE, "main_area_ratio": 1.0}))
    real = calc(FI(**BASE))
    assert real.total_revenue_ils < full.total_revenue_ils
    assert real.profit_margin_on_cost_ratio < full.profit_margin_on_cost_ratio


def test_tenant_area_is_sized_off_the_old_building_not_the_new_one():
    """אם הפיצוי נגזר מהבניין החדש, הוא צורך אותו במלואו בהגדרה — לא משנה
    כמה בונים. הבדיקה נועלת את זה: הכפלת הבניין מכפילה את חלק היזם בלבד."""
    small = calc(FI(**BASE))
    big = calc(FI(**{**BASE, "buildable_area_sqm": 6792.0}))
    assert small.tenant_allocation_sqm == big.tenant_allocation_sqm
    assert big.developer_allocation_sqm == pytest.approx(
        small.developer_allocation_sqm + 3396.0 * 0.78)


def test_extra_compensation_comes_out_of_the_developers_share():
    plain = calc(FI(**BASE, tenant_compensation_sqm_per_existing_unit=0.0))
    plus25 = calc(FI(**BASE, tenant_compensation_sqm_per_existing_unit=25.0))
    assert plus25.tenant_allocation_sqm == plain.tenant_allocation_sqm + 7 * 25.0
    assert plus25.developer_revenue_ils < plain.developer_revenue_ils


def test_the_land_is_in_the_cost_base_and_is_not_deducted_twice():
    """פיצוי הדיירים **הוא** התמורה על הקרקע. הגרסה הקודמת ניכתה אותו
    מההכנסה ולא הכניסה אותו לעלות — התשומה הגדולה ביותר מחוץ למכנה,
    ו״רווח על העלות״ החזיר 305%. הבדיקה נועלת את שתי הזהויות."""
    r = calc(FI(**BASE))
    assert r.land_cost_ils > 0
    assert r.developer_revenue_ils == pytest.approx(r.total_revenue_ils - r.land_cost_ils, abs=1)
    # לא פעמיים: הרווח זהה לחישוב ללא קרקע בשני הצדדים
    assert r.projected_profit_ils == pytest.approx(
        r.developer_revenue_ils - (r.total_cost_ils - r.land_cost_ils), abs=1)
    assert r.profit_margin_on_cost_ratio < 1.0      # מכנה שכולל את הקרקע


def test_a_building_that_cannot_rehouse_its_own_tenants_says_so(session=None):
    """‏60 דיירים ב-3,396 מ״ר החזירו חלק יזם 0 והפסד של 40 מיליון — כמו כל
    פרויקט גרעוני אחר. שום שדה לא אמר שהשיכון-מחדש עצמו אינו נכנס."""
    impossible = calc(FI(**{**BASE, "existing_units": 60}))
    assert impossible.tenants_fit is False
    assert impossible.developer_allocation_sqm == 0.0
    assert calc(FI(**BASE)).tenants_fit is True


def test_the_target_is_compared_and_not_assumed():
    """המועמד הטיפוסי מחזיר כ-34.5% -- **מעל** היעד המקובל של 20%.

    לפני B2 המספר נשען על עלות בנייה שהוערכה ידנית (10,000 ₪/מ״ר, טווח לא
    מבוסס), וההחזר נראה גבולי -- כ-17%, מתחת ליעד. אחרי שעלות הבנייה
    הוחלפה בסקר עלויות אמיתי של לשכת שמאי מקרקעין בישראל (יוני 2026, ממוצע
    ~7,367 ₪/מ״ר להרצליה+רמת השרון), אותו מועמד בדיוק נמצא **מעל** היעד.
    זו הייתה ההערכה שהשתנתה, לא הפרויקט.

    ‏15.09 (הנחות v4): מחיר המכירה ירד מ-45,000 ל-42,000 ₪ למ״ר — אומדן מוצלב
    מעסקאות יד שנייה ומפער חדש/יד שנייה — והמועמד ירד ל-~29%. עדיין מעל
    היעד של 20%, ולכן הטענה של הבדיקה לא השתנתה, רק הטווח."""
    r = calc(FI(**BASE))
    assert 0.25 < r.profit_margin_on_cost_ratio < 0.35
    assert calc(FI(**BASE, developer_profit_target_ratio=0.20)).meets_developer_target
    assert not calc(FI(**BASE, developer_profit_target_ratio=0.40)).meets_developer_target


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
    # construction_cost_per_sqm_ils is MISSING here too -- at the raw
    # assumptions-library level, before worker.py/dossier.py resolve it via
    # the developer's own figure or the appraisers' regional survey (B2, see
    # services/economic/construction_costs.py). This assertion is about the
    # library alone, not that resolution.
    assert a.blocking() == [
        "average_existing_unit_sqm", "betterment_base_ils", "construction_cost_per_sqm_ils",
    ]
    r = calc(FI(**BASE), missing_inputs=a.blocking())
    assert r.projected_profit_ils > 0          # חושב
    assert r.is_deliverable is False           # ולא נמסר
    assert "betterment_base_ils" in r.inputs_missing


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
    # ‏DATA שמורה למי שיש לה מקור חיצוני קשיח. היום שתיים: שיעור המע״מ,
    # ושיעור היטל ההשבחה — רבע ההשבחה לפי §19(ב)(10א), שנוסף בתיקון 139.
    assert sorted(n for n, x in a.report().items() if x["status"] == "data") == \
        ["betterment_levy_rate", "vat_rate"]
    # וכל הנחה שאינה DATA חייבת להסביר מאיפה המספר, או להיות MISSING.
    for name, x in a.report().items():
        assert x["source"] or x["status"] == "estimate", name


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

def test_the_margin_lands_in_a_commercially_plausible_range():
    """הגרסה הקודמת החזירה 305% רווח על העלות — אף פרויקט התחדשות אינו
    נראה כך. זו הייתה הראיה שהמודל חלקי, לא שהפרויקט מצוין."""
    r = calc(FI(**BASE))
    assert 0.0 < r.profit_margin_on_cost_ratio < 0.60


def test_every_cost_line_is_present_and_none_is_silently_zero():
    """כל שורה שהתווספה חייבת להשפיע. שורה שנשארת אפס היא שורה שלא חוברה."""
    r = calc(FI(**BASE))
    for line in ("land_cost_ils", "total_construction_cost_ils", "total_underground_cost_ils",
                 "total_soft_cost_ils", "total_demolition_cost_ils", "total_tenant_cost_ils",
                 "total_marketing_ils", "total_guarantees_ils", "total_finance_ils"):
        assert getattr(r, line) > 0, line
    parts = sum(getattr(r, n) for n in (
        "land_cost_ils", "total_construction_cost_ils", "total_underground_cost_ils",
        "total_soft_cost_ils", "total_demolition_cost_ils", "total_tenant_cost_ils",
        "total_marketing_ils", "total_guarantees_ils", "total_finance_ils",
        "betterment_levy_ils"))
    assert parts == pytest.approx(r.total_cost_ils, abs=1)


def test_a_price_quoted_with_vat_is_netted_before_it_meets_net_costs():
    """מחיר שוק מצוטט כולל מע״מ, עלויות מוצגות נטו. בלי יישור המרווח
    מנופח ב-18% עוד לפני שורת עלות אחת חסרה."""
    gross = calc(FI(**BASE, sale_price_includes_vat=True))
    net = calc(FI(**BASE, sale_price_includes_vat=False))
    assert gross.total_revenue_ils == pytest.approx(net.total_revenue_ils / 1.18, rel=1e-6)
    assert gross.profit_margin_on_cost_ratio < net.profit_margin_on_cost_ratio


def test_the_betterment_levy_is_never_silently_zero_in_the_report():
    """‏0 כערך ו-MISSING כסטטוס: לא מנוכה בשקט, וגם לא מדווח כמוכן.
    הוא לבדו יכול להפוך פרויקט, ולכן אסור לו להיעלם."""
    a = get_assumptions("herzliya")
    # השיעור ידוע בוודאות — רבע ההשבחה, §19(ב)(10א) שנוסף בתיקון 139.
    assert a.betterment_levy_rate.status is AssumptionStatus.DATA
    assert a.betterment_levy_rate.value == 0.25
    assert "139" in (a.betterment_levy_rate.source or "")
    # **ההשבחה עצמה** היא מה שחסר, והיא שומה ולא נגזרת של המכירה.
    assert a.betterment_base_ils.status is AssumptionStatus.MISSING
    assert a.betterment_base_ils.value == 0.0
    with_levy = calc(FI(**BASE, betterment_base_ils=8_000_000))
    assert with_levy.betterment_levy_ils > 0
    assert with_levy.profit_margin_on_cost_ratio < calc(FI(**BASE)).profit_margin_on_cost_ratio
