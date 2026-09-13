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
    betterment_levy_ratio: Assumption
    vat_rate: Assumption
    # The single largest deduction from the developer's share, and until now
    # it was a bare `70.0` default inside FeasibilityInput that the worker
    # never passed and the dossier never reported. Between a 55 sqm and a
    # 95 sqm average the projected profit moves by ~12.6M ILS on a typical
    # candidate. It is MISSING rather than ESTIMATE because it is knowable:
    # it is in the gramushka and the building permit, and guessing it is
    # exactly what the PRD forbids.
    average_existing_unit_sqm: Assumption

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
    version="2026-v2",
    effective_date=date(2026, 1, 1),
    sale_price_per_sqm_ils=Assumption(45_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm"),
    construction_cost_per_sqm_ils=Assumption(
        10_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm",
        source="‏8,000 לא היה ריאלי; טווח 9,500-11,000 לבנייה רוויה עם חניון"),
    demolition_cost_per_unit_ils=Assumption(150_000.0, AssumptionStatus.ESTIMATE, "ILS/unit"),
    soft_cost_ratio=Assumption(0.15, AssumptionStatus.ESTIMATE, "ratio"),
    developer_profit_target_ratio=Assumption(0.20, AssumptionStatus.ESTIMATE, "ratio"),

    main_area_ratio=Assumption(
        0.78, AssumptionStatus.ESTIMATE, "ratio",
        source="תקרת 400% כוללת שטחי שירות וממ״ד (§70ב(א)(1)); רק העיקרי נמכר במחיר דירה"),
    underground_ratio=Assumption(
        0.40, AssumptionStatus.ESTIMATE, "ratio",
        source="חניון תת-קרקעי אינו נספר בתקרה אך נבנה ומשולם"),
    underground_cost_per_sqm_ils=Assumption(6_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm"),

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
        source="שיווק ותיווך, טווח מקובל 2%-3% מההכנסות"),
    guarantees_ratio=Assumption(
        0.0125, AssumptionStatus.ESTIMATE, "ratio",
        source="ערבויות חוק המכר וביטוח, 1%-1.5% מההכנסות"),
    finance_ratio=Assumption(
        0.06, AssumptionStatus.ESTIMATE, "ratio",
        source="ליווי בנקאי וריבית, טווח מקובל 5%-7% מהעלויות"),
    # ‏50% מההשבחה. בפינוי-בינוי ובתמ״א 38 היו פטורים; **האם קיים פטור
    # בחלופת שקד לפי תיקון 139 טרם נבדק.** הוא לבדו יכול להכריע פרויקט,
    # ולכן הוא MISSING עם ערך 0 — לא מנוכה בשקט, וגם לא מדווח כמוכן.
    betterment_levy_ratio=Assumption(
        0.0, AssumptionStatus.MISSING, "ratio",
        source="היטל השבחה 50% מההשבחה — קיומו של פטור בתיקון 139 שאלה פתוחה לעו״ד"),
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
