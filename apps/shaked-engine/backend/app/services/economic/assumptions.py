"""
Commercial assumptions library for the "Generic Report 0" scenario
(Shaked PRD section 6.4).

The PRD requires (ECO-02) that every material commercial input be either a
substantiated value or an explicit, approved model assumption -- never a
bare magic number -- and that "the assumptions library carries a date and
version" (6.4), with each component "marked as data, estimate, or missing."
This module is that library: a named, versioned, dated, per-city set of
assumptions, each tagged with where it stands.

Every entry below is currently ESTIMATE, not DATA: none of these figures
have been sourced from a real appraiser, market survey, or municipal
schedule. They exist so the pipeline has something explicit and inspectable
to compute against -- not because they're correct. Replace with sourced
DATA entries (and bump the version) before using this for a real decision.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum


class AssumptionStatus(str, Enum):
    DATA = "data"  # a real, cited figure (market survey, appraiser, municipal schedule)
    ESTIMATE = "estimate"  # a reasoned placeholder, not yet sourced
    MISSING = "missing"  # genuinely unknown -- must block a "ready" result, not default to zero


@dataclass(frozen=True)
class Assumption:
    value: float
    status: AssumptionStatus
    unit: str
    source: str | None = None


@dataclass(frozen=True)
class EconomicAssumptionSet:
    city_code: str
    version: str
    effective_date: date
    sale_price_per_sqm_ils: Assumption
    construction_cost_per_sqm_ils: Assumption
    demolition_cost_per_unit_ils: Assumption
    soft_cost_ratio: Assumption
    developer_profit_target_ratio: Assumption

    # ── שטח נמכר מול שטח בנוי ──
    main_area_ratio: Assumption
    underground_ratio: Assumption
    underground_cost_per_sqm_ils: Assumption

    # ── פיצוי הדיירים ──
    # The single largest deduction from the developer's share, and until now
    # `average_existing_unit_sqm` was a bare `70.0` default inside
    # FeasibilityInput that the worker never passed and the dossier never
    # reported. Between a 55 sqm and a 95 sqm average the projected profit
    # moves by millions on a typical candidate. It is MISSING rather than
    # ESTIMATE because it is knowable: it is in the gramushka and the
    # building permit, and guessing it is exactly what the PRD forbids.
    average_existing_unit_sqm: Assumption
    tenant_compensation_sqm_per_existing_unit: Assumption
    tenant_rent_months: Assumption
    tenant_monthly_rent_ils: Assumption
    tenant_moving_cost_ils: Assumption
    tenant_legal_cost_per_unit_ils: Assumption

    # ── שיעורים ──
    marketing_ratio: Assumption
    guarantees_ratio: Assumption
    finance_ratio: Assumption
    betterment_levy_rate: Assumption
    betterment_base_ils: Assumption
    vat_rate: Assumption

    def blocking(self) -> list[str]:
        """Assumptions that are genuinely unknown.

        `AssumptionStatus.MISSING` was defined here from the start with the
        comment "must block a 'ready' result, not default to zero", and then
        nothing ever read it -- no entry carried the status and no code
        branched on it. This is the reader.
        """
        return sorted(
            name for name, field in self.__dataclass_fields__.items()
            if isinstance(getattr(self, name), Assumption)
            and getattr(self, name).status is AssumptionStatus.MISSING
        )

    def report(self) -> dict[str, dict]:
        """Every assumption with its value and status, for the dossier.

        Built from the dataclass fields rather than hand-listed: the
        hand-written version in worker.py silently omitted two of them.
        """
        return {name: {"value": a.value, "status": a.status.value,
                       "unit": a.unit, "source": a.source}
                for name in self.__dataclass_fields__
                if isinstance(a := getattr(self, name), Assumption)}


HERZLIYA_2026_V1 = EconomicAssumptionSet(
    city_code="herzliya",
    version="2026-v5",
    effective_date=date(2026, 1, 1),
    # ‏v4 (15.09.2026): 45,000 → 42,000, ועם מקור. 45,000 היה ניחוש אחיד לעיר.
    # ‏42,000 מוצלב משני מקורות, ועדיין אומדן ולא נתון:
    #   1. ‏GovMap — 44 עסקאות יד שנייה ברדיוס 500 מ׳ מחלקות ההדגמה, 12 חודשים:
    #      חציון 32,883 ₪ למ״ר (B16, issue #18).
    #   2. מדלן, הרצליה, 15.09.2026 (צפייה ידנית, לא שליפה): דירה חדשה יקרה בכ-40%
    #      מיד שנייה באותו מספר חדרים (3 חד׳ +38%, 4 +41%, 5 +40%). הפער הוא
    #      למחיר דירה; דירה חדשה גדולה יותר (ממ״ד), ולכן למ״ר כ-25%–30%.
    #   ‏32,883 × 1.25–1.30 ≈ 41,000–43,000.
    # **לא מכניסים עליית מחירים צפויה:** התיק מתאר את השוק ביום הבדיקה, והטעות
    # היקרה היא מחיר גבוה מדי — הוא הופך חלקה גבולית ל״כדאית״.
    sale_price_per_sqm_ils=Assumption(
        42_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm",
        source="אומדן לדירה חדשה בהרצליה: עסקאות יד שנייה ליד החלקות (GovMap) × פער חדש/יד שנייה בעיר (מדלן, 15.09.2026)"),
    # Superseded by `services/economic/construction_costs.py`: the developer's
    # own figure, then the appraisers' regional survey, decide this value now
    # (see worker.py). This entry only feeds a scenario when neither is
    # available -- for Herzliya the survey always covers it, so in practice
    # this is dead weight kept for cities the survey doesn't reach yet.
    construction_cost_per_sqm_ils=Assumption(
        7_366.67, AssumptionStatus.MISSING, "ILS/sqm",
        source="Placeholder only -- no developer figure and no appraisers' survey entry for this city"),
    # ‏B8 · שלוש השורות האלה הוצגו בתיק עם מקור ריק (״—״). אין להן מקור
    # שנשלף, ולכן המקור אומר בדיוק את זה — ולא מצטט טווח ״מקובל״ שאיש לא בדק.
    demolition_cost_per_unit_ils=Assumption(
        150_000.0, AssumptionStatus.ESTIMATE, "ILS/unit",
        source="הנחת עבודה — לא נשלפה ממקור; היזם מחליף בהצעת מחיר"),
    soft_cost_ratio=Assumption(
        0.15, AssumptionStatus.ESTIMATE, "ratio",
        source="הנחת עבודה, כשיעור מעלות הבנייה — לא נשלפה ממקור"),
    # ‏v5 · 15.09 (בועז): *״הרווח היזמי חייב להיות מעל 16% כדי שיהיה כדאי״*.
    # מספר אחד לכל התיק — הסימון ליד הרווח, תקרת ההיטל (ההיטל שמשאיר 16%)
    # ושווי הקרקע השיורי שממנו נגזר אומדן ההיטל. היה 20%, והמשפט כאן אמר
    # שהוא ״קובע את סף ההשבחה״ בזמן שהסף חושב עד רווח אפס.
    developer_profit_target_ratio=Assumption(
        0.16, AssumptionStatus.ESTIMATE, "ratio",
        source="רווח יזמי מזערי לכדאיות, על העלות (בועז, 15.09) — קובע את הסימון ליד הרווח, "
               "את תקרת ההיטל ואת אומדן ההיטל; אינו משנה את הרווח"),

    main_area_ratio=Assumption(
        0.78, AssumptionStatus.ESTIMATE, "ratio",
        source="תקרת 400% כוללת שטחי שירות וממ״ד (§70ב(א)(1)); רק העיקרי נמכר במחיר דירה"),
    underground_ratio=Assumption(
        0.40, AssumptionStatus.ESTIMATE, "ratio",
        source="חניון תת-קרקעי אינו נספר בתקרה אך נבנה ומשולם"),
    # ‏**גיבוי בלבד.** להרצליה המספר נקבע ב-`construction_costs.py` מסקר
    # לשכת שמאי המקרקעין (3,900 ₪). הערך כאן משמש רק עיר שהסקר לא מכסה.
    underground_cost_per_sqm_ils=Assumption(
        6_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm",
        source="גיבוי לעיר שאינה בסקר השמאים — להרצליה נקבע ב-construction_costs.py"),

    average_existing_unit_sqm=Assumption(
        70.0, AssumptionStatus.MISSING, "sqm",
        source="נדרש מהגרמושקה או מהיתר הבנייה — 70 הוא מציין מקום לחישוב, לא נתון"),
    tenant_compensation_sqm_per_existing_unit=Assumption(
        25.0, AssumptionStatus.ESTIMATE, "sqm", source="תוספת מקובלת בהתחדשות עירונית"),
    tenant_rent_months=Assumption(
        42.0, AssumptionStatus.ESTIMATE, "months", source="תקופת בנייה 3.5 שנים"),
    tenant_monthly_rent_ils=Assumption(
        7_500.0, AssumptionStatus.ESTIMATE, "ILS/month",
        source="שכ״ד לדירת 4 חדרים בהרצליה — טווח, לא נתון שנשלף"),
    tenant_moving_cost_ils=Assumption(
        10_000.0, AssumptionStatus.ESTIMATE, "ILS/unit", source="שתי הובלות"),
    tenant_legal_cost_per_unit_ils=Assumption(
        30_000.0, AssumptionStatus.ESTIMATE, "ILS/unit",
        source="עו״ד ושמאי לדיירים, על חשבון היזם"),

    marketing_ratio=Assumption(
        0.025, AssumptionStatus.ESTIMATE, "ratio",
        source="שיווק ותיווך, טווח מקובל 2%-3% מהכנסות הדירות שהיזם מוכר"),
    guarantees_ratio=Assumption(
        0.0125, AssumptionStatus.ESTIMATE, "ratio",
        source="ערבויות חוק המכר וביטוח, 1%-1.5% מההכנסות"),
    finance_ratio=Assumption(
        0.06, AssumptionStatus.ESTIMATE, "ratio",
        source="ליווי בנקאי וריבית, טווח מקובל 5%-7% מהעלויות — בלי שווי דירות הבעלים"),
    # ── היטל השבחה: השיעור ידוע בוודאות, הבסיס לא ──
    #
    # תיקון 139 הוסיף את סעיף 19(ב)(10א) לתוספת השלישית, וקבע שיעור
    # **מופחת** לתכנית לפי סימן ד׳ — מסלול הריסה (§70ב) ומסלול חיזוק
    # (§70ד): *״יחול היטל בשיעור **רבע ההשבחה**״*, ולא מחצית. השיעור חל
    # על כל ההשבחה מאותה תכנית, גם אם נכללו בה הוראות לפי §62א.
    #
    # שלושה סייגים שנמצאו באותו מקור:
    #   · אינו חל על מתחם פינוי-בינוי (ס״ק (ה))
    #   · חל רק על מימוש **בהיתר**, לא במכר
    #   · רשות מקומית רשאית להפחית לשמינית או לפטור מלא, בהחלטת מועצה
    #     רוחבית אחת לשלוש שנים (§19(ב)(ב2)) — **לא נמצא פרסום כזה
    #     בהרצליה**, וזו שאלה לפרוטוקולי המועצה.
    betterment_levy_rate=Assumption(
        0.25, AssumptionStatus.DATA, "ratio",
        source="‏§19(ב)(10א)(א) לתוספת השלישית, שנוסף בתיקון 139 — רבע ההשבחה"),

    # **זה מה שחסר.** ההיטל הוא רבע מ*ההשבחה* — עליית שווי המקרקעין
    # שנובעת מהתכנית — ולא אחוז מההכנסות. את ההשבחה עצמה קובע שמאי.
    betterment_base_ils=Assumption(
        0.0, AssumptionStatus.MISSING, "ILS",
        source="ההשבחה עצמה — עליית שווי המקרקעין בשל התכנית. נדרשת שומה"),
    vat_rate=Assumption(0.18, AssumptionStatus.DATA, "ratio",
                        source="שיעור המע״מ בישראל"),
)

ASSUMPTIONS_BY_CITY: dict[str, EconomicAssumptionSet] = {
    "herzliya": HERZLIYA_2026_V1,
}


def get_assumptions(city_code: str) -> EconomicAssumptionSet:
    try:
        return ASSUMPTIONS_BY_CITY[city_code]
    except KeyError as exc:
        raise ValueError(f"No economic assumptions library entry for city '{city_code}'") from exc
