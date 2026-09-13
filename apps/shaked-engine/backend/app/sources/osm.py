"""
OpenStreetMap building footprints, via Overpass.

Ported from POC/app/sources.py (public_buildings) onto AsyncPublicClient. OSM is
a community source: it is good for finding buildings, never for deciding
anything about them, so every footprint is marked `authority: community` and
its evidence can only ever be `Certainty.COMMUNITY`.
"""

from typing import Any

from shapely.geometry import Polygon, mapping, shape

from app.geo import center_selected, itm
from app.sources.client import AsyncPublicClient, SourceError

OVERPASS = "https://overpass-api.de/api/interpreter"


async def public_buildings(client: AsyncPublicClient, polygon_wgs: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Closed, valid building ways whose centroid falls inside the search area, in ITM, sorted by id."""
    minx, miny, maxx, maxy = shape(polygon_wgs).bounds
    query = f'[out:json][timeout:25];way["building"]({miny},{minx},{maxy},{maxx});out tags geom;'
    data, meta = await client.json(OVERPASS, {"data": query})
    if data.get("remark"):
        raise SourceError(data["remark"])

    scope = itm(polygon_wgs)
    selected: list[dict[str, Any]] = []
    for element in data.get("elements", []):
        coords = [(point["lon"], point["lat"]) for point in element.get("geometry", [])]
        if len(coords) < 4 or coords[0] != coords[-1]:
            continue
        geom = itm(Polygon(coords))
        if not geom.is_valid or geom.area == 0 or not center_selected(geom, scope):
            continue
        selected.append(
            {
                "id": f"osm:way:{element['id']}",
                "geometry": mapping(geom),
                "properties": element.get("tags", {}),
                "_source": dict(
                    meta,
                    feature_url=f"https://www.openstreetmap.org/way/{element['id']}",
                    source_updated_at=data.get("osm3s", {}).get("timestamp_osm_base"),
                ),
                "authority": "community",
            }
        )
    if len(selected) > limit:
        raise SourceError(f"Building limit exceeded ({limit}); draw a smaller area")
    return sorted(selected, key=lambda feature: feature["id"])
