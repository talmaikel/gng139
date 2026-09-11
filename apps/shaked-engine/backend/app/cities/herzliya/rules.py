from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.base import BaseCityRules, UnificationResult
from app.cities.herzliya.candidates import screen_herzliya_candidates
from app.cities.herzliya.unification import check_unification
from app.cities.herzliya.xplan_schema import is_eligible_residential_code

# Herzliya's minimum combined plot area for a "Shaked Alternative" urban-renewal lot.
HERZLIYA_MINIMUM_PLOT_AREA_SQM = 1000.0


class HerzliyaCityRules(BaseCityRules):
    city_code = "herzliya"
    display_name = "Herzliya"

    async def screen_candidates(self, session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
        return await screen_herzliya_candidates(session, filters)

    def is_eligible_xplan_code(self, xplan_code: str) -> bool:
        try:
            return is_eligible_residential_code(int(xplan_code))
        except (TypeError, ValueError):
            return False

    async def check_plot_unification(self, session: AsyncSession, parcel_ids: list[str]) -> UnificationResult:
        return await check_unification(session, parcel_ids, self.minimum_plot_area_sqm())

    def minimum_plot_area_sqm(self) -> float:
        return HERZLIYA_MINIMUM_PLOT_AREA_SQM
