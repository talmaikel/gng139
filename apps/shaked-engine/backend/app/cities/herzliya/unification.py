"""
Plot-unification checks for Herzliya using PostGIS spatial predicates.

Two or more parcels may be combined into a single "Shaked Alternative" buildable
lot only if the parcels dissolve into ONE contiguous shape and the unioned area
clears the municipal minimum plot threshold. "Every parcel touches another" is
not the same test and is not enough — see `_is_connected`.
"""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.base import UnificationResult
from app.models.opportunity import Opportunity


async def _is_connected(session: AsyncSession, parcel_ids: list[str]) -> bool:
    """
    True if the parcels form ONE connected shape.

    The previous implementation asserted something weaker: that no parcel is
    isolated. That is not connectivity. Two adjacent pairs 1.7 km apart each
    satisfy "every parcel touches another parcel in the set", so the check
    passed and `_unioned_area_sqm` summed two unrelated plots into one lot
    that clears the municipal minimum. Nothing in the result said they were
    not contiguous.

    Dissolving the set and counting what is left answers the real question:
    polygons that share an edge merge into one, and anything disconnected
    survives as its own part of the MultiPolygon.
    """
    stmt = text(
        """
        SELECT ST_NumGeometries(ST_Multi(ST_Union(geom))) = 1 AS connected
        FROM opportunities
        WHERE id = ANY(:ids)
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

    if not await _is_connected(session, parcel_ids):
        return UnificationResult(
            is_unifiable=False,
            combined_area_sqm=0.0,
            parcel_ids=parcel_ids,
            reason="The parcels do not form one contiguous shape",
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
