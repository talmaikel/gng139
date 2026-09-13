import httpx
import pytest
from shapely.geometry import box

from app.sources.arcgis import ArcGIS
from app.sources.client import AsyncPublicClient, SourceError
from tests.conftest import no_wait


def arcgis(tmp_path, handler, base):
    return ArcGIS(AsyncPublicClient(tmp_path, transport=httpx.MockTransport(handler), sleep=no_wait), base)


# ---- ported from POC/tests/test_core.py --------------------------------------


async def test_proxy_target_query_separator(tmp_path):
    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"layers": []})

    service = arcgis(tmp_path, response, "http://arcgis005/arcgis/rest/services/a/MapServer")
    with pytest.raises(SourceError):
        await service.discover("buildings")
    assert "/MapServer?f=json" in calls[0]


# ---- added with the port ---------------------------------------------------------


async def test_a_short_feature_page_is_refused_as_truncated(tmp_path):
    def response(request):
        if request.url.params.get("returnIdsOnly") == "true":
            return httpx.Response(200, json={"objectIds": [1, 2, 3]})
        return httpx.Response(200, json={"features": [{"id": 1}]})

    service = arcgis(tmp_path, response, "https://gis.example.org/arcgis/rest/services/b/MapServer")
    with pytest.raises(SourceError, match="truncated"):
        await service.features({"id": 0}, {"maxRecordCount": 100}, box(0, 0, 10, 10))


async def test_an_ambiguous_layer_name_is_refused(tmp_path):
    layers = {"layers": [{"id": 1, "name": "מבנים"}, {"id": 2, "name": "מבנים ישנים"}]}
    service = arcgis(tmp_path, lambda r: httpx.Response(200, json=layers), "https://gis.example.org/MapServer")
    with pytest.raises(SourceError, match="ambiguous"):
        await service.discover("מבנים")
