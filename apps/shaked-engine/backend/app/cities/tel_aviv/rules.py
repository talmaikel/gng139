"""
Stub Tel Aviv strategy — demonstrates that adding a new municipality only
requires implementing BaseCityRules, with zero changes to the rest of the
backend. Fill in real XPlan codes, screening queries and unification rules
before onboarding Tel Aviv opportunities.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.base import BaseCityRules, UnificationResult

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
