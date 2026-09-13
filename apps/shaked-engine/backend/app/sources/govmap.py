"""
GovMap open-data WFS: municipal boundaries and cadastral parcels.

Ported from POC/app/sources.py (GovMap) onto AsyncPublicClient. Pagination is
checked, not trusted: a feature served twice, a result larger than the limit, or
a stream that ends before the count it advertised all raise, because a silently
short parcel list looks exactly like a complete one.
"""

import xml.etree.ElementTree as ET
from typing import Any

from shapely.geometry.base import BaseGeometry

from app.sources.client import AsyncPublicClient, SourceError

WFS = "https://open.govmap.gov.il/geoserver/opendata/wfs"
BOUNDARY_LAYER = "opendata:muni_il"
PARCEL_LAYER = "opendata:Parcels_ITM"
PARCEL_FIELDS = ("GUSH_NUM", "GUSH_SUFFI", "PARCEL", "LEGAL_AREA", "SYS_DATE")


def parcel_key(feature: dict[str, Any]) -> tuple[str, int, str]:
    """(gush, sub-gush suffix, parcel): the stable identity of a cadastral parcel."""
    props = feature["properties"]
    return str(props["GUSH_NUM"]), int(props.get("GUSH_SUFFI") or 0), str(props["PARCEL"])


class GovMap:
    def __init__(self, client: AsyncPublicClient):
        self.client = client

    async def discover(self) -> list[str]:
        raw, _ = await self.client.get(WFS, {"service": "WFS", "request": "GetCapabilities"})
        root = ET.fromstring(raw)
        types = [element.text for element in root.findall(".//{*}FeatureType/{*}Name")]
        for required in (BOUNDARY_LAYER, PARCEL_LAYER):
            if required not in types:
                raise SourceError(f"Missing WFS layer: {required}")
        return types

    async def schema(self, layer: str, required: tuple[str, ...] | list[str]) -> set[str]:
        data, _ = await self.client.json(
            WFS,
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "DescribeFeatureType",
                "typeNames": layer,
                "outputFormat": "application/json",
            },
        )
        names = {prop["name"] for prop in data["featureTypes"][0]["properties"]}
        if not set(required) <= names:
            raise SourceError(f"WFS schema changed: {layer}")
        return names

    async def features(self, layer: str, cql: str, limit: int = 300, page_size: int = 100) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        offset = 0
        while True:
            data, meta = await self.client.json(
                WFS,
                {
                    "service": "WFS",
                    "version": "2.0.0",
                    "request": "GetFeature",
                    "typeNames": layer,
                    "outputFormat": "application/json",
                    "srsName": "EPSG:2039",
                    "CQL_FILTER": cql,
                    "count": page_size,
                    "startIndex": offset,
                },
            )
            if data.get("type") != "FeatureCollection":
                raise SourceError("Invalid WFS feature response")
            batch = data["features"]
            total = data.get("numberMatched")
            for feature in batch:
                if feature["id"] in seen:
                    raise SourceError("WFS repeated a feature; pagination may be incomplete")
                seen.add(feature["id"])
                feature["_source"] = dict(meta)
                result.append(feature)
            if len(result) > limit:
                raise SourceError(f"Parcel limit exceeded ({limit}); draw a smaller area")
            offset += len(batch)
            if isinstance(total, int) and offset >= total:
                break
            if not batch:
                if isinstance(total, int) and offset < total:
                    raise SourceError("WFS ended before the advertised count")
                break
            if len(batch) < page_size and not isinstance(total, int):
                break
        return result

    async def boundary(self, lamas_code: str, expected_name: str) -> dict[str, Any]:
        """The one municipal boundary feature for a city, e.g. ("6400", "הרצליה")."""
        await self.discover()
        await self.schema(BOUNDARY_LAYER, ["CR_LAMAS", "Muni_Heb"])
        rows = await self.features(BOUNDARY_LAYER, f"CR_LAMAS='{lamas_code}'", 10)
        if len(rows) != 1 or rows[0]["properties"]["Muni_Heb"] != expected_name:
            raise SourceError(f"{expected_name} boundary not uniquely identified")
        return rows[0]

    async def parcels(self, polygon_itm: BaseGeometry, limit: int = 300) -> list[dict[str, Any]]:
        await self.schema(PARCEL_LAYER, PARCEL_FIELDS)
        bounds = ",".join(str(round(x, 3)) for x in polygon_itm.bounds)
        return await self.features(PARCEL_LAYER, f"BBOX(the_geom,{bounds},'EPSG:2039')", limit)
