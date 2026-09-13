from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities import get_city_rules as _get_city_rules
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.tenant import User
from app.cities.herzliya.archive_facts import fetch_for_delivery
from app.services.deliveries import (NoCredits, NotDeliverable, deliver, delivered_ids,
                                     for_company, provenance)

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
    filters = body.model_dump()
    # מה שכבר נמסר לחברה אינו מוצע שוב כהזדמנות חדשה — הוא נשאר במאגר שלה.
    filters["exclude_delivered_ids"] = await delivered_ids(session, user.company_id)
    try:
        return await rules.screen_candidates(session, filters)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.get("/{city_code}/mine")
async def my_deliveries(
    city_code: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """מאגר המסירות של החברה — ‏SEL-02: *״מוצג במאגר החברה בלבד״*."""
    get_city_rules(city_code)
    return await for_company(session, user.company_id)


@router.post("/{city_code}/{opportunity_id}/deliver")
async def deliver_opportunity(
    city_code: str,
    opportunity_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """מוסר הזדמנות לחברה ומנכה זכאות. קריאה חוזרת אינה מחייבת שוב.

    מועמד שתנאי הסף שלו לא נשאל — תיק הבניין נשלף **כאן**, בבקשה הזו,
    ואז המסירה מנוסה שוב. השליפה, ההערכה מחדש והמסירה הן עסקה אחת: תיק
    שנשלף ומסירה שנכשלה אחריו אינם יכולים להישאר במצבים שונים.
    """
    get_city_rules(city_code)
    try:
        # ‏SEL-01: הגרסאות והנימוק נקראים **אחרי** שהמועמד הוכן — אם התיק
        # נשלף בבקשה הזו, גרסת הנתונים חייבת לכלול אותו.
        async def prepare(s, oid):
            return await fetch_for_delivery(s, oid)

        row, charged = await deliver(session, opportunity_id, user.company_id, user.id,
                                     on_unready=prepare)
        if charged:
            p = await provenance(session, opportunity_id)
            row.rules_version, row.data_version, row.why_selected = (
                p["rules_version"], p["data_version"], p["why"])
            await session.flush()
    except NotDeliverable as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except NoCredits as e:
        raise HTTPException(status_code=402, detail=str(e)) from e
    await session.commit()
    return {"delivery_id": str(row.id), "opportunity_id": str(row.opportunity_id),
            "charged": charged, "delivered_at": row.delivered_at.isoformat()}


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
        "exclude_delivered_ids": await delivered_ids(session, user.company_id),
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
