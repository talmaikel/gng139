from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities import get_city_rules
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.tenant import User

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/{city_code}")
async def list_candidates(
    city_code: str,
    min_area_sqm: float | None = Query(default=None),
    verification_level: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """Pre-filtered candidate opportunities for a given city, applying the city's own strategy."""
    rules = get_city_rules(city_code)
    filters = {
        "min_area_sqm": min_area_sqm,
        "verification_level": verification_level,
        "limit": limit,
    }
    return await rules.screen_candidates(session, filters)


@router.post("/{city_code}/unify")
async def check_unification(
    city_code: str,
    parcel_ids: list[str],
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Check whether a set of adjacent parcels can be unified into one buildable lot."""
    rules = get_city_rules(city_code)
    result = await rules.check_plot_unification(session, parcel_ids)
    return {
        "is_unifiable": result.is_unifiable,
        "combined_area_sqm": result.combined_area_sqm,
        "parcel_ids": result.parcel_ids,
        "reason": result.reason,
    }
