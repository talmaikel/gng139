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
    assert r.constructed_area_sqm == pytest.approx(3396.0 * 1.60)  # ועוד חניון (דוחות 0: 56%–77%)
    assert r.total_underground_cost_ils > 0
    assert r.sellable_main_sqm == pytest.approx(3396.0 * 0.85)    # ורק זה נמכר (דוחות 0: 82%–90%)
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
        small.developer_allocation_sqm + 3396.0 * 0.85)


def test_extra_compensation_comes_out_of_the_developers_share():
    plain = calc(FI(**BASE, tenant_compensation_sqm_per_existing_unit=0.0))
    plus25 = calc(FI(**BASE, tenant_compensation_sqm_per_existing_unit=25.0))
    assert plus25.tenant_allocation_sqm == plain.tenant_allocation_sqm + 7 * 25.0
    assert plus25.developer_revenue_ils < plain.developer_revenue_ils


def test_the_owners_flats_are_neither_revenue_nor_cost():
    """‏16.09 · ״רווחיות מעלויות״ כמו בדוח 0. פיצוי הדיירים **הוא** התמורה על
    הקרקע: הוא מוצג, ואינו נספר לא כהכנסה ולא כעלות. הגרסה הקודמת ספרה
    אותו בשני הצדדים — הרווח בשקלים לא השתנה, אבל המכנה כמעט הוכפל, ו-16%
    שלנו היה רף כפול מ-16% של היזם (גולומב 17: 16.5% בדוח, 10.4% אצלנו)."""
    r = calc(FI(**BASE))
    assert r.owners_flats_value_ils > 0
    assert r.total_revenue_ils == pytest.approx(r.developer_revenue_ils, abs=1)
    assert r.projected_profit_ils == pytest.approx(r.total_revenue_ils - r.total_cost_ils, abs=1)
    # דירות הבעלים אינן במכנה: הכפלת שווין (מחיר כפול) אינה מכפילה את העלות
    parts = sum(getattr(r, n) for n in COST_LINES)
    assert parts == pytest.approx(r.total_cost_ils, abs=1)
    assert r.owners_flats_value_ils == pytest.approx(
        r.tenant_allocation_sqm * BASE["sale_price_per_sqm"] / 1.18, abs=1)


def test_balconies_are_built_for_everyone_and_sold_only_on_the_developers_flats():
    """בדוחות 0 כל דירה חדשה מקבלת 12 מ״ר מרפסת שאינה בשטח המותר, נבנית
    ב-2,500 ₪ ונמכרת בחצי מחיר מ״ר עיקרי."""
    r = calc(FI(**BASE))
    assert r.new_units_estimate >= 7
    assert r.balcony_sqm == pytest.approx(r.new_units_estimate * 12.0)
    assert r.total_balcony_cost_ils == pytest.approx(r.balcony_sqm * 2_500.0)
    share = r.developer_allocation_sqm / r.sellable_main_sqm
    assert r.balcony_revenue_ils == pytest.approx(
        r.balcony_sqm * share * 0.5 * BASE["sale_price_per_sqm"] / 1.18, abs=1)
    assert r.developer_revenue_ils == pytest.approx(
        r.developer_allocation_sqm * BASE["sale_price_per_sqm"] / 1.18 + r.balcony_revenue_ils, abs=1)
    none = calc(FI(**BASE, balcony_sqm_per_new_unit=0.0))
    assert none.balcony_revenue_ils == 0 and none.total_balcony_cost_ils == 0


def test_a_building_that_cannot_rehouse_its_own_tenants_says_so(session=None):
    """‏60 דיירים ב-3,396 מ״ר החזירו חלק יזם 0 והפסד של 40 מיליון — כמו כל
    פרויקט גרעוני אחר. שום שדה לא אמר שהשיכון-מחדש עצמו אינו נכנס."""
    impossible = calc(FI(**{**BASE, "existing_units": 60}))
    assert impossible.tenants_fit is False
    assert impossible.developer_allocation_sqm == 0.0
    assert calc(FI(**BASE)).tenants_fit is True


def test_the_target_is_compared_and_not_assumed():
    """המועמד הטיפוסי מחזיר כ-62% -- **מעל** היעד.

    לפני B2 המספר נשען על עלות בנייה שהוערכה ידנית (10,000 ₪/מ״ר, טווח לא
    מבוסס), וההחזר נראה גבולי -- כ-17%, מתחת ליעד. אחרי שעלות הבנייה
    הוחלפה בסקר עלויות אמיתי של לשכת שמאי מקרקעין בישראל (יוני 2026, ממוצע
    ~7,367 ₪/מ״ר להרצליה+רמת השרון), אותו מועמד בדיוק נמצא **מעל** היעד.
    זו הייתה ההערכה שהשתנתה, לא הפרויקט.

    ‏15.09 (הנחות v4): מחיר המכירה ירד מ-45,000 ל-42,000 ₪ למ״ר, והמועמד ירד ל-~29%.

    ‏16.09 (הנחות v6): ״רווחיות מעלויות״ כמו בדוח 0 — דירות הבעלים יצאו
    מהמכנה — ואותו מועמד קורא ~62%. זה אותו רווח בשקלים על מכנה קטן
    בהרבה: ‏3,396 מ״ר לשבע דירות של 70 מ״ר הוא פרויקט נדיר, והמדידה החדשה
    אומרת זאת במספר."""
    r = calc(FI(**BASE))
    assert 0.55 < r.profit_margin_on_cost_ratio < 0.70
    assert calc(FI(**BASE, developer_profit_target_ratio=0.20)).meets_developer_target
    assert not calc(FI(**BASE, developer_profit_target_ratio=0.80)).meets_developer_target


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
    # ‏E1 · ~9.7 מיליון: המימון אינו מחושב יותר על שווי דירות הבעלים.
    assert spread > 9_000_000


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
    # ‏DATA שמורה למי שיש לה מקור חיצוני קשיח. היום שלוש: שיעור המע״מ,
    # שיעור היטל ההשבחה — רבע ההשבחה לפי §19(ב)(10א), שנוסף בתיקון 139 —
    # ושיעור מס הרכישה על מקרקעין שאינם דירת מגורים.
    assert sorted(n for n, x in a.report().items() if x["status"] == "data") == \
        ["betterment_levy_rate", "purchase_tax_ratio", "vat_rate"]
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
    נראה כך. זו הייתה הראיה שהמודל חלקי, לא שהפרויקט מצוין.

    ‏16.09 · במדידה של דוח 0 (דירות הבעלים מחוץ למכנה) פרויקט טוב במיוחד
    קורא עשרות אחוזים, ולא מאות. גולומב 17 — פרויקט אמיתי — הוא 16.5%."""
    r = calc(FI(**BASE))
    assert 0.0 < r.profit_margin_on_cost_ratio < 1.0


COST_LINES = ("total_construction_cost_ils", "total_underground_cost_ils", "total_balcony_cost_ils",
              "total_soft_cost_ils", "total_demolition_cost_ils", "total_tenant_cost_ils",
              "total_consultants_ils", "total_fees_ils", "purchase_tax_ils",
              "total_marketing_ils", "total_guarantees_ils", "total_bank_fees_ils",
              "total_finance_ils", "betterment_levy_ils")


def test_every_cost_line_is_present_and_none_is_silently_zero():
    """כל שורה שהתווספה חייבת להשפיע. שורה שנשארת אפס היא שורה שלא חוברה."""
    r = calc(FI(**BASE))
    for line in COST_LINES:
        if line != "betterment_levy_ils":          # ההשבחה MISSING, ולכן 0 בכוונה
            assert getattr(r, line) > 0, line
    parts = sum(getattr(r, n) for n in COST_LINES)
    assert parts == pytest.approx(r.total_cost_ils, abs=1)


def test_the_report_0_cost_lines_are_what_the_reports_charge():
    """‏16.09 · השורות שנוספו מהדוחות, כל אחת עם הנוסחה שלה."""
    inp = FI(**BASE)
    r = calc(inp)
    assert r.total_demolition_cost_ils == 250_000            # לבניין, ״קומפלט״
    assert r.total_fees_ils == pytest.approx(r.constructed_area_sqm * 300.0)
    assert r.purchase_tax_ils == pytest.approx(0.06 * 12_000.0 * r.developer_allocation_sqm)
    assert r.total_consultants_ils == pytest.approx(r.new_units_estimate * 50_000.0 + 150_000.0)
    assert r.total_tenant_cost_ils == pytest.approx(
        7 * (36 * 7_500.0 + 16_000.0 + 30_000.0) + 250_000.0)
    before_finance = r.total_cost_ils - r.total_finance_ils - r.total_bank_fees_ils
    assert r.total_bank_fees_ils == pytest.approx(before_finance * 0.013, abs=1)
    assert r.total_finance_ils == pytest.approx(before_finance * 0.04, abs=1)


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


def test_marketing_and_finance_are_not_charged_on_the_owners_flats():
    """‏E1 · 15.09 (בועז). שווי דירות הבעלים היה בבסיס של שיווק ושל מימון.
    באלוף יגאל אלון 40 אלה היו כ-3.2 ו-7.6 מיליון ₪ על דירות שאיש אינו
    משווק ושווי שאיש אינו מממן. ‏16.09: הוא כבר אינו עלות בכלל, והמימון
    מחושב על כל העלויות לפני מימון."""
    inp = FI(**BASE)
    r = calc(inp)
    assert r.total_marketing_ils == pytest.approx(r.developer_revenue_ils * inp.marketing_ratio, abs=1)
    before_finance = r.total_cost_ils - r.total_finance_ils - r.total_bank_fees_ils
    assert r.total_finance_ils == pytest.approx(before_finance * inp.finance_ratio, abs=1)
    assert r.owners_flats_value_ils > 0 and r.owners_flats_value_ils not in (
        before_finance, r.total_cost_ils)
    # ערבויות נשארות על הכול: היזם נותן ערבויות גם לבעלים
    assert r.total_guarantees_ils == pytest.approx(
        (r.total_revenue_ils + r.owners_flats_value_ils) * inp.guarantees_ratio, abs=1)
