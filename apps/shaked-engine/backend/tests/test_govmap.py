import httpx
import pytest

from app.sources.client import AsyncPublicClient, SourceError
from app.sources.govmap import GovMap, parcel_key
from tests.conftest import no_wait


def govmap(tmp_path, handler):
    return GovMap(AsyncPublicClient(tmp_path, transport=httpx.MockTransport(handler), sleep=no_wait))


# ---- ported from POC/tests/test_core.py --------------------------------------


async def test_wfs_pages_and_truncation(tmp_path):
    def response(request):
        start = int(request.url.params["startIndex"])
        batch = [{"id": str(i), "geometry": None, "properties": {}} for i in range(start, min(start + 2, 5))]
        return httpx.Response(200, json={"type": "FeatureCollection", "numberMatched": 5, "features": batch})

    assert len(await govmap(tmp_path / "a", response).features("layer", "1=1", limit=5, page_size=2)) == 5
    with pytest.raises(SourceError):
        await govmap(tmp_path / "b", response).features("layer", "1=1", limit=4, page_size=2)


async def test_repeated_pages_rejected(tmp_path):
    def response(request):
        return httpx.Response(200, json={"type": "FeatureCollection", "numberMatched": 5, "features": [{"id": "x"}]})

    with pytest.raises(SourceError, match="repeated"):
        await govmap(tmp_path, response).features("layer", "1=1", 10, 1)


# ---- added with the port ---------------------------------------------------------


async def test_a_stream_that_ends_before_its_advertised_count_is_refused(tmp_path):
    def response(request):
        batch = [{"id": "a"}] if request.url.params["startIndex"] == "0" else []
        return httpx.Response(200, json={"type": "FeatureCollection", "numberMatched": 3, "features": batch})

    with pytest.raises(SourceError, match="advertised"):
        await govmap(tmp_path, response).features("layer", "1=1", 10, 1)


CAPABILITIES = (
    b'<WFS_Capabilities><FeatureTypeList>'
    b"<FeatureType><Name>opendata:muni_il</Name></FeatureType>"
    b"<FeatureType><Name>opendata:Parcels_ITM</Name></FeatureType>"
    b"</FeatureTypeList></WFS_Capabilities>"
)


def boundary_service(features):
    def handler(request):
        kind = request.url.params.get("request")
        if kind == "GetCapabilities":
            return httpx.Response(200, content=CAPABILITIES)
        if kind == "DescribeFeatureType":
            return httpx.Response(200, json={"featureTypes": [{"properties": [{"name": "CR_LAMAS"}, {"name": "Muni_Heb"}]}]})
        return httpx.Response(200, json={"type": "FeatureCollection", "numberMatched": len(features), "features": features})

    return handler


async def test_a_boundary_must_be_one_feature_carrying_the_expected_name(tmp_path):
    herzliya = {"id": "muni.1", "properties": {"CR_LAMAS": "6400", "Muni_Heb": "הרצליה"}, "geometry": None}
    assert (await govmap(tmp_path / "one", boundary_service([herzliya])).boundary("6400", "הרצליה"))["id"] == "muni.1"

    twice = [herzliya, {**herzliya, "id": "muni.2"}]
    with pytest.raises(SourceError, match="uniquely"):
        await govmap(tmp_path / "two", boundary_service(twice)).boundary("6400", "הרצליה")

    renamed = [{**herzliya, "properties": {"CR_LAMAS": "6400", "Muni_Heb": "רעננה"}}]
    with pytest.raises(SourceError, match="uniquely"):
        await govmap(tmp_path / "renamed", boundary_service(renamed)).boundary("6400", "הרצליה")


def test_parcel_key_includes_the_sub_gush_suffix():
    assert parcel_key({"properties": {"GUSH_NUM": 6529, "GUSH_SUFFI": 2, "PARCEL": 167}}) == ("6529", 2, "167")
    assert parcel_key({"properties": {"GUSH_NUM": 6529, "GUSH_SUFFI": None, "PARCEL": 167}}) == ("6529", 0, "167")
