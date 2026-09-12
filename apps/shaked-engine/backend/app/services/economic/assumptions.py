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


HERZLIYA_2026_V1 = EconomicAssumptionSet(
    city_code="herzliya",
    version="2026-v1",
    effective_date=date(2026, 1, 1),
    sale_price_per_sqm_ils=Assumption(45_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm"),
    construction_cost_per_sqm_ils=Assumption(8_000.0, AssumptionStatus.ESTIMATE, "ILS/sqm"),
    demolition_cost_per_unit_ils=Assumption(150_000.0, AssumptionStatus.ESTIMATE, "ILS/unit"),
    soft_cost_ratio=Assumption(0.15, AssumptionStatus.ESTIMATE, "ratio"),
    developer_profit_target_ratio=Assumption(0.20, AssumptionStatus.ESTIMATE, "ratio"),
)

ASSUMPTIONS_BY_CITY: dict[str, EconomicAssumptionSet] = {
    "herzliya": HERZLIYA_2026_V1,
}


def get_assumptions(city_code: str) -> EconomicAssumptionSet:
    try:
        return ASSUMPTIONS_BY_CITY[city_code]
    except KeyError as exc:
        raise ValueError(f"No economic assumptions library entry for city '{city_code}'") from exc
