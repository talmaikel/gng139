"""
Regional construction-cost fallback for the feasibility calculator (B2).

`construction_cost_per_sqm` in a feasibility scenario should first come from
the developer running that specific project -- they know their own
contractor pricing better than any survey. When they do not supply one,
this module is the fallback: a table lifted from the Israeli Association of
Real Estate Appraisers' construction-cost survey (REPORT_SOURCE), a real,
dated, cited figure rather than an invented one.

The survey breaks each region into three building-height bands (low-rise,
high-rise, multi-story) plus a separate underground rate. When a floor count
is known, `cost_for_floors` picks the survey's own band for that building;
only when it is not (the archive-driven worker path) does the fallback average
the three. Either way the above-ground figure is reported as an ESTIMATE --
a band choice or an average, not a figure measured for this building -- and a
developer's own figure, once supplied, always wins.

The underground rate has no bands, so `resolve_underground_cost_per_sqm`
returns it as DATA.
"""

from dataclasses import dataclass
from datetime import date

REPORT_SOURCE = "לשכת שמאי מקרקעין בישראל — אומדן עלויות בנייה, יוני 2026"
REPORT_EFFECTIVE_DATE = date(2026, 6, 1)

# The survey classifies a building by the height difference between the
# entry floor and the top residential floor: low-rise up to 13m, high-rise
# up to 29m, multi-story above that. Nothing in this codebase measures a
# building in metres, but the dossier's rights assessment does carry a floor
# count -- so these thresholds translate the survey's bands into floors, at
# a typical ~3m residential storey height (13m / 3m ~ 4, 29m / 3m ~ 9-10).
# A building at 7-9 floors, which is what the Shaked Alternative typically
# produces, lands in the high-rise band -- not an average across all three.
LOW_RISE_MAX_FLOORS = 4
HIGH_RISE_MAX_FLOORS = 9


@dataclass(frozen=True)
class RegionalConstructionCost:
    region_label: str
    low_rise_ils_per_sqm: float
    high_rise_ils_per_sqm: float
    multi_story_ils_per_sqm: float
    underground_ils_per_sqm: float

    @property
    def average_above_ground_ils_per_sqm(self) -> float:
        return round(
            (self.low_rise_ils_per_sqm + self.high_rise_ils_per_sqm + self.multi_story_ils_per_sqm) / 3, 2
        )

    def cost_for_floors(self, floors: float) -> tuple[float, str]:
        """The survey's own band for a building of this floor count.

        Ties go to the taller band on purpose: overstating construction cost
        understates profit, which is the direction a feasibility estimate
        should err in when the exact height is not certain.
        """
        if floors <= LOW_RISE_MAX_FLOORS:
            return self.low_rise_ils_per_sqm, "בניין נמוך"
        if floors <= HIGH_RISE_MAX_FLOORS:
            return self.high_rise_ils_per_sqm, "בניין גבוה"
        return self.multi_story_ils_per_sqm, "בניין רב קומות"


# One row per city currently onboarded. Add a row here (from the same
# survey) before onboarding a new city -- the survey does not group cities
# by proximity, and neither should this table.
REGIONAL_CONSTRUCTION_COSTS: dict[str, RegionalConstructionCost] = {
    "herzliya": RegionalConstructionCost(
        region_label="הרצליה + רמת השרון",
        low_rise_ils_per_sqm=7_000.0,
        high_rise_ils_per_sqm=7_200.0,
        multi_story_ils_per_sqm=7_900.0,
        underground_ils_per_sqm=3_900.0,
    ),
}


@dataclass(frozen=True)
class ConstructionCostResolution:
    value_ils_per_sqm: float | None
    status: str  # "data" | "estimate" | "missing"
    source: str
    method: str  # "developer_input" | "appraisers_survey_regional_average" | "none"
    as_of_date: date | None


def resolve_construction_cost_per_sqm(
    city_code: str, developer_value: float | None, floors: float | None = None
) -> ConstructionCostResolution:
    """Decide what the calculator should use, and how it must be reported.

    A developer's own figure for their own project beats a regional survey
    figure every time it is supplied: it is not a claim about the market, so
    it needs no source citation and carries `status="data"`. Only when they
    supply nothing does this fall back to the survey, and then only for a
    city the survey actually covers -- an uncovered city returns
    `status="missing"` rather than reusing another region's numbers.

    `floors` picks the survey's own height band for this specific building
    (see `RegionalConstructionCost.cost_for_floors`) instead of averaging
    across all three -- pass it whenever a floor count is known. Leave it
    `None` when it is not (e.g. the archive-driven pipeline in worker.py,
    which has no rights assessment to read a floor count from); the fallback
    is then the three-band average, still marked `estimate`.
    """
    if developer_value is not None:
        return ConstructionCostResolution(
            value_ils_per_sqm=round(developer_value, 2),
            status="data",
            source="developer_provided",
            method="developer_input",
            as_of_date=None,
        )

    region = REGIONAL_CONSTRUCTION_COSTS.get(city_code)
    if region is not None:
        if floors is not None:
            value, band_label = region.cost_for_floors(floors)
            return ConstructionCostResolution(
                value_ils_per_sqm=value,
                status="estimate",
                source=f"{REPORT_SOURCE} ({region.region_label}, {band_label})",
                method="appraisers_survey_by_building_height",
                as_of_date=REPORT_EFFECTIVE_DATE,
            )
        return ConstructionCostResolution(
            value_ils_per_sqm=region.average_above_ground_ils_per_sqm,
            status="estimate",
            source=f"{REPORT_SOURCE} ({region.region_label}, ממוצע שלוש רמות גובה -- מספר קומות לא ידוע)",
            method="appraisers_survey_regional_average",
            as_of_date=REPORT_EFFECTIVE_DATE,
        )

    return ConstructionCostResolution(
        value_ils_per_sqm=None,
        status="missing",
        source="No developer figure and no appraisers' survey entry for this city",
        method="none",
        as_of_date=None,
    )


def resolve_underground_cost_per_sqm(city_code: str) -> ConstructionCostResolution:
    """עלות מ״ר תת-קרקעי — מאותו סקר, מאותה שורה בטבלה.

    הטבלה החזיקה את המספר הזה מהיום הראשון (3,900 ₪ להרצליה), והמחשבון
    לא קרא אותו: הוא המשיך לקרוא 6,000 מספריית ההנחות. כלומר חצי מהסקר
    נטען ולא שימש, ועלות החניון נופחה ב-54% — כ-6.7 מיליון ₪ בפרויקט
    טיפוסי.

    **מסומן `estimate`, כמו העלות העילית מאותו סקר.** בגרסה הראשונה סומן
    ‏`data`, בנימוק שאין כאן בחירה בין רמות גובה. הנימוק שגוי: העלות
    העילית מסומנת `estimate` גם כשמספר הקומות ידוע ואין ממוצע — כי סקר
    אזורי הוא טענה על השוק ולא הנתון של הפרויקט; רק מספר שהיזם מסר הוא
    ‏`data`. שתי שורות מאותה טבלה בתיק, אחת ״נתון״ ואחת ״אומדן״, סתרו
    זו את זו (A20).
    הסקר מציין שהמספר **אינו כולל ביסוס**: הביסוס מגולם בעלות העילית.
    """
    region = REGIONAL_CONSTRUCTION_COSTS.get(city_code)
    if region is None:
        return ConstructionCostResolution(
            value_ils_per_sqm=None, status="missing",
            source="No appraisers' survey entry for this city",
            method="none", as_of_date=None)
    return ConstructionCostResolution(
        value_ils_per_sqm=region.underground_ils_per_sqm,
        status="estimate",
        source=f"{REPORT_SOURCE} ({region.region_label}, מ״ר תת-קרקעי, אינו כולל ביסוס)",
        method="appraisers_survey_underground",
        as_of_date=REPORT_EFFECTIVE_DATE,
    )
