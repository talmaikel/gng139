"""
Geometry in the Israeli grid.

Ported from POC/app/geo.py. Areas, radii and overlaps are computed in ITM
(EPSG:2039) metres, never in degrees; WGS84 (EPSG:4326) is only for storage and
the map. Search areas are validated against the city's official boundary before
anything is fetched, and a building is attributed to the parcels it actually
overlaps, not to the nearest one.
"""

from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

TO_ITM = Transformer.from_crs(4326, 2039, always_xy=True).transform
TO_WGS = Transformer.from_crs(2039, 4326, always_xy=True).transform

MAX_POLYGON_VERTICES = 500
MIN_PARCEL_OVERLAP = 0.02  # a sliver below 2% of the footprint is drawing noise, not an attribution


def itm(geo: dict[str, Any] | BaseGeometry) -> BaseGeometry:
    return transform(TO_ITM, shape(geo) if isinstance(geo, dict) else geo)


def wgs(geom: BaseGeometry) -> dict[str, Any]:
    return mapping(transform(TO_WGS, geom))


def validate_polygon(geo: dict[str, Any], boundary: BaseGeometry, max_area_sqm: float) -> BaseGeometry:
    """A drawn search area, in ITM, after checking it is simple, bounded and inside the city."""
    polygon = shape(geo)
    if (
        polygon.geom_type != "Polygon"
        or polygon.is_empty
        or not polygon.is_valid
        or len(polygon.exterior.coords) > MAX_POLYGON_VERTICES
    ):
        raise ValueError("הפוליגון אינו תקין; יש לצייר אזור ללא חצייה עצמית")
    polygon = itm(polygon)
    if polygon.area <= 0 or polygon.area > max_area_sqm:
        raise ValueError(f"מגבלת האזור היא {max_area_sqm / 1000:g} דונם")
    if not boundary.covers(polygon):
        raise ValueError("כל אזור החיפוש חייב להיות בתוך הגבול העירוני הרשמי")
    return polygon


def circle_polygon(
    center: dict[str, float],
    radius_m: float,
    boundary: BaseGeometry,
    max_radius_m: float,
    max_area_sqm: float,
) -> BaseGeometry:
    """The authoritative circular search area, built in ITM metres."""
    if not isinstance(center, dict) or set(center) != {"lat", "lon"}:
        raise ValueError("יש לבחור נקודת מרכז תקינה")
    lat, lon, radius = float(center["lat"]), float(center["lon"]), float(radius_m)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("נקודת המרכז אינה קואורדינטה תקינה")
    if radius <= 0 or radius > max_radius_m:
        raise ValueError(f"הרדיוס המרבי הוא {max_radius_m:g} מטר")
    polygon = transform(TO_ITM, Point(lon, lat)).buffer(radius, quad_segs=32)
    if polygon.area > max_area_sqm:
        raise ValueError(f"מגבלת האזור היא {max_area_sqm / 1000:g} דונם")
    # Covering the official boundary is the real "is this in the city" test.
    if not boundary.covers(polygon):
        raise ValueError("כל מעגל החיפוש חייב להיות בתוך הגבול העירוני הרשמי")
    return polygon


def center_selected(building: BaseGeometry, area: BaseGeometry) -> bool:
    """A building belongs to a search area by its centroid; boundary points count, as with covers()."""
    return area.covers(building.centroid)


def match_parcels(building: BaseGeometry, parcels: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    """Parcels a footprint overlaps, largest share first; ties break on parcel id for a stable order."""
    matches = []
    for parcel in parcels:
        overlap = building.intersection(shape(parcel["geometry"])).area / building.area if building.area else 0
        if overlap > MIN_PARCEL_OVERLAP:
            matches.append((overlap, parcel))
    matches.sort(key=lambda item: (-item[0], str(item[1]["id"])))
    return matches


def pair_geometry(a: BaseGeometry, b: BaseGeometry, public_separation_verified: bool) -> BaseGeometry | None:
    """
    Two parcels as one planning unit, only when they share a real boundary and
    it is verified that no public road or open space separates them.
    """
    if not public_separation_verified:
        return None
    if a.intersection(b).area > 0.01 or a.boundary.intersection(b.boundary).length < 0.1:
        return None
    return unary_union([a, b])
