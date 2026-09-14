"""
Tel Aviv-Yafo — stub, parked as a future expansion. See README.md in this folder.

Registered in CITY_REGISTRY to demonstrate that adding a municipality touches
nothing outside app/cities/. Every method raises NotImplementedError except
minimum_plot_area_sqm, whose 1500 sqm value is a PLACEHOLDER: it was not taken
from any Tel Aviv policy document and must not be treated as a rule.

Everything already known about Tel Aviv (the SharePoint archive connector, the
document taxonomy, three David Hamelech dossiers, timings and blockers) lives in
POC/app/tel_aviv.py and POC/data/cities/tel-aviv/README.md. Do not develop here
until the expansion is decided.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.base import BaseCityRules, UnificationResult

# PLACEHOLDER — not from any Tel Aviv policy source. See README.md.
TEL_AVIV_MINIMUM_PLOT_AREA_SQM = 1500.0


class TelAvivCityRules(BaseCityRules):
    city_code = "tel_aviv"
    display_name = "Tel Aviv-Yafo"

    async def screen_candidates(self, session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("Tel Aviv candidate screening is not yet implemented")

    def is_eligible_xplan_code(self, xplan_code: str) -> bool:
        raise NotImplementedError("Tel Aviv XPlan eligibility rules are not yet implemented")

    async def check_plot_unification(self, session: AsyncSession, parcel_ids: list[str]) -> UnificationResult:
        raise NotImplementedError("Tel Aviv plot unification rules are not yet implemented")

    def minimum_plot_area_sqm(self) -> float:
        return TEL_AVIV_MINIMUM_PLOT_AREA_SQM
