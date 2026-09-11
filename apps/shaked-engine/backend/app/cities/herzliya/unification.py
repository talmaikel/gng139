"""
Plot-unification checks for Herzliya using PostGIS spatial predicates.

Two or more parcels may be combined into a single "Shaked Alternative" buildable
lot only if every parcel touches at least one other parcel in the set (so the
whole set forms one connected shape) and the unioned area clears the municipal
minimum plot threshold.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.base import UnificationResult
from app.models.opportunity import Opportunity


async def _all_touch_within_set(session: AsyncSession, parcel_ids: list[str]) -> bool:
    """
    True if the parcels form one connected group under ST_Touches, i.e. no
    parcel in the set is isolated from the rest.
    """
    stmt = text(
        """
        SELECT count(*) = 0 AS fully_connected
        FROM opportunities a
        WHERE a.id = ANY(:ids)
          AND NOT EXISTS (
              SELECT 1 FROM opportunities b
              WHERE b.id = ANY(:ids)
                AND b.id <> a.id
                AND ST_Touches(a.geom, b.geom)
          )
        """
    )
    result = await session.execute(stmt, {"ids": parcel_ids})
    row = result.first()
    return bool(row and row[0])


async def _unioned_area_sqm(session: AsyncSession, parcel_ids: list[str]) -> float:
    stmt = text(
        """
        SELECT ST_Area(ST_Union(geom)::geography)
        FROM opportunities
        WHERE id = ANY(:ids)
        """
    )
    result = await session.execute(stmt, {"ids": parcel_ids})
    area = result.scalar()
    return float(area or 0.0)


async def check_unification(
    session: AsyncSession, parcel_ids: list[str], minimum_area_sqm: float
) -> UnificationResult:
    if len(parcel_ids) < 2:
        return UnificationResult(
            is_unifiable=False,
            combined_area_sqm=0.0,
            parcel_ids=parcel_ids,
            reason="At least two parcels are required for unification",
        )

    existing = await session.execute(select(Opportunity.id).where(Opportunity.id.in_(parcel_ids)))
    found_ids = {str(row[0]) for row in existing.all()}
    missing = set(parcel_ids) - found_ids
    if missing:
        return UnificationResult(
            is_unifiable=False,
            combined_area_sqm=0.0,
            parcel_ids=parcel_ids,
            reason=f"Unknown parcel id(s): {sorted(missing)}",
        )

    if not await _all_touch_within_set(session, parcel_ids):
        return UnificationResult(
            is_unifiable=False,
            combined_area_sqm=0.0,
            parcel_ids=parcel_ids,
            reason="Not every parcel touches another parcel in the set",
        )

    combined_area = await _unioned_area_sqm(session, parcel_ids)
    if combined_area < minimum_area_sqm:
        return UnificationResult(
            is_unifiable=False,
            combined_area_sqm=combined_area,
            parcel_ids=parcel_ids,
            reason=f"Combined area {combined_area:.1f} sqm is below the minimum {minimum_area_sqm:.1f} sqm",
        )

    return UnificationResult(is_unifiable=True, combined_area_sqm=combined_area, parcel_ids=parcel_ids)
