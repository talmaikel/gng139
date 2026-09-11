"""Pre-filtered candidate screening for Herzliya opportunities."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.herzliya.xplan_schema import QUEUE_ELIGIBLE_CATEGORIES
from app.models.opportunity import Opportunity


async def screen_herzliya_candidates(session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return pre-filtered candidate addresses for Herzliya, restricted to
    opportunities whose XPlan screening category is queue-eligible
    (`primary_candidate` / `needs_verification`) unless the caller overrides it.
    """
    stmt = select(Opportunity).where(Opportunity.city_code == "herzliya")

    categories = filters.get("categories") or list(QUEUE_ELIGIBLE_CATEGORIES)
    stmt = stmt.where(Opportunity.metadata_json["category"].astext.in_(categories))

    if min_area := filters.get("min_area_sqm"):
        stmt = stmt.where(Opportunity.area_sqm >= min_area)

    if verification_level := filters.get("verification_level"):
        stmt = stmt.where(Opportunity.verification_level == verification_level)

    stmt = stmt.limit(int(filters.get("limit", 100)))

    result = await session.execute(stmt)
    opportunities = result.scalars().all()
    return [
        {
            "id": str(opp.id),
            "address": opp.address,
            "block": opp.block,
            "parcel": opp.parcel,
            "xplan_code": opp.xplan_code,
            "area_sqm": opp.area_sqm,
            "verification_level": opp.verification_level,
            "category": opp.metadata_json.get("category"),
        }
        for opp in opportunities
    ]
