"""Pre-filtered candidate screening for Herzliya opportunities."""

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.herzliya.xplan_schema import QUEUE_ELIGIBLE_CATEGORIES
from app.models.opportunity import Opportunity
from app.cities.herzliya.boundary import search_polygon_wkt


async def screen_herzliya_candidates(session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return pre-filtered candidate addresses for Herzliya, restricted to
    opportunities whose XPlan screening category is queue-eligible
    (`primary_candidate` / `needs_verification`) unless the caller overrides it.
    """
    geometry_geojson = func.ST_AsGeoJSON(Opportunity.geom)
    centroid = func.ST_Centroid(Opportunity.geom)
    centroid_lat = func.ST_Y(centroid)
    centroid_lng = func.ST_X(centroid)

    stmt = select(Opportunity, geometry_geojson, centroid_lat, centroid_lng).where(
        Opportunity.city_code == "herzliya"
    )

    # אזור חיפוש מצויר. הסינון נעשה ב-PostGIS ולא ב-Python: 699 פוליגונים
    # הם מעט, אבל המדד המרחבי קיים והשאילתה אמורה להישאר זולה גם כשיהיו יותר.
    if (poly := filters.get("polygon")) is not None:
        stmt = stmt.where(
            func.ST_Intersects(Opportunity.geom, func.ST_GeomFromText(search_polygon_wkt(poly), 4326))
        )

    categories = filters.get("categories") or list(QUEUE_ELIGIBLE_CATEGORIES)
    stmt = stmt.where(Opportunity.metadata_json["category"].astext.in_(categories))

    if min_area := filters.get("min_area_sqm"):
        stmt = stmt.where(Opportunity.area_sqm >= min_area)

    # מועמד שנפסל בשערים אינו מוצג כלל. מי שאין לו קביעת קומות אינו
    # "מדורג נמוך" אלא אינו בר-מסירה — זו מוכנות, לא העדפה.
    stmt = stmt.where(Opportunity.metadata_json["assessment"]["status"].astext != "ineligible")
    if filters.get("deliverable_only"):
        stmt = stmt.where(Opportunity.metadata_json["assessment"]["deliverable"].astext == "true")

    if verification_level := filters.get("verification_level"):
        stmt = stmt.where(Opportunity.verification_level == verification_level)

    stmt = stmt.limit(int(filters.get("limit", 100)))

    result = await session.execute(stmt)
    return [
        {
            "id": str(opp.id),
            "address": opp.address,
            "block": opp.block,
            "parcel": opp.parcel,
            "xplan_code": opp.xplan_code,
            "area_sqm": opp.area_sqm,
            "existing_units": opp.existing_units,
            "verification_level": opp.verification_level,
            "category": opp.metadata_json.get("category"),
            "assessment": opp.metadata_json.get("assessment"),
            "geometry": json.loads(geojson) if geojson else None,
            "centroid": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
        }
        for opp, geojson, lat, lng in result.all()
    ]
