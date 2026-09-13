"""
ArcGIS REST map services, including municipal ones reached through GISNET's proxy.

Ported from POC/app/sources.py (ArcGIS) onto AsyncPublicClient. A layer is
chosen only when exactly one matches, and a page that returns fewer features
than the ids asked for is treated as truncated rather than as the full answer.
"""

import json
import re
from typing import Any
from urllib.parse import urlsplit

from shapely.geometry.base import BaseGeometry

from app.sources.client import AsyncPublicClient, SourceError

GISNET_PROXY = "https://v5.gis-net.co.il/proxy/proxy.ashx?"
PROXIED_HOSTS = {"arcgis005"}  # internal hosts the public GISNET application exposes only through its proxy


class ArcGIS:
    def __init__(self, client: AsyncPublicClient, base: str):
        self.client = client
        self.base = base.rstrip("/")

    def url(self, suffix: str = "") -> str:
        # Only the service URL returned by the public application is proxied.
        target = self.base + suffix
        if urlsplit(target).hostname in PROXIED_HOSTS:
            return GISNET_PROXY + target + "?"
        return target

    async def discover(self, name_pattern: str) -> tuple[dict[str, Any], dict[str, Any]]:
        data, _ = await self.client.json(self.url(), {"f": "json"})
        candidates = [
            layer
            for layer in data.get("layers", [])
            if re.search(name_pattern, layer["name"]) and layer.get("subLayerIds") is None
        ]
        if len(candidates) != 1:
            raise SourceError(f"Layer mapping ambiguous or unavailable: {name_pattern}")
        layer = candidates[0]
        schema, _ = await self.client.json(self.url("/" + str(layer["id"])), {"f": "json"})
        if schema.get("geometryType") != "esriGeometryPolygon":
            raise SourceError("Expected a polygon layer")
        return layer, schema

    async def features(
        self, layer: dict[str, Any], schema: dict[str, Any], polygon_itm: BaseGeometry, limit: int = 100
    ) -> list[dict[str, Any]]:
        url = self.url("/" + str(layer["id"]) + "/query")
        geometry = json.dumps({"rings": [list(polygon_itm.exterior.coords)], "spatialReference": {"wkid": 2039}})
        ids, _ = await self.client.json(
            url,
            {
                "f": "json",
                "where": "1=1",
                "geometry": geometry,
                "geometryType": "esriGeometryPolygon",
                "inSR": 2039,
                "spatialRel": "esriSpatialRelIntersects",
                "returnIdsOnly": "true",
            },
        )
        object_ids = ids.get("objectIds") or []
        if len(object_ids) > limit:
            raise SourceError("Building limit exceeded")
        output: list[dict[str, Any]] = []
        size = min(schema.get("maxRecordCount", 100), 100)
        for start in range(0, len(object_ids), size):
            selected = object_ids[start : start + size]
            data, meta = await self.client.json(
                url,
                {
                    "f": "geojson",
                    "objectIds": ",".join(map(str, selected)),
                    "outFields": "*",
                    "returnGeometry": "true",
                    "outSR": 2039,
                },
            )
            if len(data.get("features", [])) != len(selected) or data.get("exceededTransferLimit"):
                raise SourceError("ArcGIS response truncated")
            for feature in data["features"]:
                feature["_source"] = meta
            output += data["features"]
        return output
