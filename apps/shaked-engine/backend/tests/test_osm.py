import httpx
import pytest
from shapely.geometry import box, mapping

from app.sources.client import AsyncPublicClient, SourceError
from app.sources.osm import public_buildings
from tests.conftest import no_wait

AREA = mapping(box(34.838, 32.162, 34.841, 32.164))


def overpass(tmp_path, elements, remark=None):
    body = {"elements": elements, "osm3s": {"timestamp_osm_base": "2026-09-10T00:00:00Z"}}
    if remark:
        body["remark"] = remark
    return AsyncPublicClient(tmp_path, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)), sleep=no_wait)


def way(way_id, lon, lat, size=0.0002, closed=True):
    ring = [(lon, lat), (lon + size, lat), (lon + size, lat + size), (lon, lat + size)]
    if closed:
        ring.append(ring[0])
    return {"id": way_id, "tags": {"building": "yes"}, "geometry": [{"lon": x, "lat": y} for x, y in ring]}


async def test_buildings_are_chosen_by_centroid_and_marked_as_a_community_source(tmp_path):
    inside, outside, unclosed = way(1, 34.839, 32.163), way(2, 34.845, 32.163), way(3, 34.8395, 32.1632, closed=False)
    rows = await public_buildings(overpass(tmp_path, [inside, outside, unclosed]), AREA, limit=10)
    assert [row["id"] for row in rows] == ["osm:way:1"]
    assert rows[0]["authority"] == "community"
    assert rows[0]["_source"]["feature_url"] == "https://www.openstreetmap.org/way/1"
    assert rows[0]["_source"]["source_updated_at"] == "2026-09-10T00:00:00Z"


async def test_an_overpass_remark_is_an_error_not_an_empty_area(tmp_path):
    with pytest.raises(SourceError, match="timed out"):
        await public_buildings(overpass(tmp_path, [], remark="runtime error: Query timed out"), AREA, limit=10)


async def test_the_building_limit_is_enforced_rather_than_cut(tmp_path):
    elements = [way(i, 34.8385 + i * 0.0005, 32.1625) for i in range(3)]
    with pytest.raises(SourceError, match="limit"):
        await public_buildings(overpass(tmp_path, elements), AREA, limit=2)
