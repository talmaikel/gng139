"""
Strategy-pattern interface for city-specific "Shaked Alternative" logic.

Each municipality has its own XPlan designation codes, minimum-plot thresholds,
and adjacency rules for unifying neighboring parcels into a single buildable lot.
Concrete cities (e.g. app/cities/herzliya) implement this interface; the rest of
the backend (candidate screening, economic calculator, dossier pipeline) depends
only on BaseCityRules, never on a specific city module.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class UnificationResult:
    """Result of attempting to unify a set of adjacent parcels into one lot."""

    is_unifiable: bool
    combined_area_sqm: float
    parcel_ids: list[str]
    reason: str | None = None


class BaseCityRules(ABC):
    """Every supported municipality implements this contract."""

    city_code: str
    display_name: str

    @abstractmethod
    async def screen_candidates(self, session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
        """Return pre-filtered candidate addresses/parcels for this city, honoring `filters`."""
        raise NotImplementedError

    @abstractmethod
    def is_eligible_xplan_code(self, xplan_code: str) -> bool:
        """Whether a given municipal XPlan designation code qualifies under this city's Shaked rules."""
        raise NotImplementedError

    @abstractmethod
    async def check_plot_unification(self, session: AsyncSession, parcel_ids: list[str]) -> UnificationResult:
        """Whether a set of parcels are adjacent/touching and may be unified into one buildable lot."""
        raise NotImplementedError

    @abstractmethod
    def minimum_plot_area_sqm(self) -> float:
        """Minimum combined plot area required by this municipality's planning rules."""
        raise NotImplementedError
