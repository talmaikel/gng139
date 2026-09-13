from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities import get_city_rules as _get_city_rules
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.tenant import User

router = APIRouter(prefix="/candidates", tags=["candidates"])


def get_city_rules(city_code: str):
    """‏`ValueError` על עיר לא רשומה הגיע ללקוח כ-500 — שגיאת שרת על קלט
    של משתמש. עיר שאינה קיימת היא 404."""
    try:
        return _get_city_rules(city_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class Preference(BaseModel):
    """העדפת מיון אחת. ‏PRD 4.2: היזם מגדיר סדר מפורש, לא משקולות."""
    field: Literal["parcel_area", "units", "floors", "cap_400"]
    direction: Literal["asc", "desc"] = "desc"


class SearchArea(BaseModel):
    """אזור חיפוש מצויר, GeoJSON Polygon ב-WGS84, עם תנאי חובה וסדר העדפות."""
    polygon: dict[str, Any]
    min_area_sqm: float | None = None
    deliverable_only: bool = False
    # שלוש לכל היותר — מעבר לכך הסדר מפסיק להיות מובן למי שהגדיר אותו.
    preferences: list[Preference] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=100, le=500)


@router.post("/{city_code}/search")
async def search_candidates(
    city_code: str,
    body: SearchArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """מועמדים בתוך אזור מצויר. פוליגון שאינו תקין או חורג מהעיר נדחה ב-422."""
    rules = get_city_rules(city_code)
    try:
        return await rules.screen_candidates(session, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{city_code}")
async def list_candidates(
    city_code: str,
    min_area_sqm: float | None = Query(default=None),
    verification_level: str | None = Query(default=None),
    deliverable_only: bool = Query(default=False,
        description="רק מועמדים שההערכה שלהם ניתנת למסירה — לא מנותבים למתחמים ולא ללא קביעת קומות"),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """Pre-filtered candidate opportunities for a given city, applying the city's own strategy."""
    rules = get_city_rules(city_code)
    filters = {
        "min_area_sqm": min_area_sqm,
        "verification_level": verification_level,
        "deliverable_only": deliverable_only,
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
