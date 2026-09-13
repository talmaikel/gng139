import httpx
import pytest

from app.sources.client import MAX_BODY_BYTES, AsyncPublicClient, HostPolicy, SourceError

UNPACED = {"example.org": HostPolicy(min_interval_seconds=0)}


def make_client(tmp_path, handler, policies=UNPACED):
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = AsyncPublicClient(tmp_path, transport=httpx.MockTransport(handler), policies=policies, sleep=fake_sleep)
    return client, sleeps


# ---- ported from POC/tests/test_core.py --------------------------------------


async def test_html_200_is_not_success(tmp_path):
    client, _ = make_client(tmp_path, lambda r: httpx.Response(200, text="<html>404</html>"))
    with pytest.raises(SourceError, match="Expected JSON"):
        await client.json("https://example.org")


async def test_cache_retains_original_retrieval_time(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    client, _ = make_client(tmp_path, handler)
    _, first = await client.json("https://example.org")
    _, second = await client.json("https://example.org")
    assert first == second and len(calls) == 1


# ---- added with the port ---------------------------------------------------------


async def test_retryable_status_honours_retry_after_then_succeeds(tmp_path):
    responses = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": True})])
    client, sleeps = make_client(tmp_path, lambda r: next(responses))
    data, _ = await client.json("https://example.org/a")
    assert data == {"ok": True} and 7.0 in sleeps


async def test_client_error_is_not_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    client, _ = make_client(tmp_path, handler)
    with pytest.raises(SourceError, match="HTTP 404"):
        await client.get("https://example.org/missing")
    assert len(calls) == 1


async def test_gives_up_after_three_attempts_without_a_final_wait(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    client, sleeps = make_client(tmp_path, handler)
    with pytest.raises(SourceError, match="HTTP 503"):
        await client.get("https://example.org/down")
    assert len(calls) == 3 and sleeps == [1.0, 2.0]


async def test_overpass_backs_off_on_its_own_slot_cycle(tmp_path):
    responses = iter([httpx.Response(504), httpx.Response(504), httpx.Response(200, json={"elements": []})])
    client, sleeps = make_client(tmp_path, lambda r: next(responses), policies={})
    await client.json("https://overpass-api.de/api/interpreter", {"data": "[out:json];"})
    assert sleeps.count(15.0) == 2


async def test_archive_requests_are_paced_ten_seconds_apart(tmp_path):
    client, sleeps = make_client(tmp_path, lambda r: httpx.Response(200, text="ok"), policies={})
    await client.get("https://handasi.complot.co.il/magicscripts/mgrqispi.dll", {"t": 1})
    await client.get("https://handasi.complot.co.il/magicscripts/mgrqispi.dll", {"t": 2})
    assert any(9.5 < s <= 10.0 for s in sleeps)


async def test_oversized_body_is_refused_not_truncated(tmp_path):
    client, _ = make_client(tmp_path, lambda r: httpx.Response(200, content=b"x" * (MAX_BODY_BYTES + 1)))
    with pytest.raises(SourceError, match="25 MB"):
        await client.get("https://example.org/huge")


async def test_params_fold_into_one_replayable_url(tmp_path):
    client, _ = make_client(tmp_path, lambda r: httpx.Response(200, json={"layers": []}))
    _, meta = await client.json("https://example.org/a", {"f": "json", "where": "1=1"})
    assert meta["url"] == "https://example.org/a?f=json&where=1%3D1"
    _, meta = await client.json("https://example.org/proxy.ashx?https://inner/MapServer?", {"f": "json"})
    assert meta["url"].endswith("MapServer?f=json")


async def test_post_cache_is_keyed_on_the_payload(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.content)
        return httpx.Response(200, json={"d": []})

    client, _ = make_client(tmp_path, handler)
    await client.post_json("https://example.org/streets", {"site_id": "121"})
    await client.post_json("https://example.org/streets", {"site_id": "121"})
    _, meta = await client.post_json("https://example.org/streets", {"site_id": "122"})
    assert len(calls) == 2 and meta["method"] == "POST" and meta["request"] == {"site_id": "122"}


async def test_every_response_carries_its_hash_and_retrieval_time(tmp_path):
    client, _ = make_client(tmp_path, lambda r: httpx.Response(200, content=b'{"a":1}'))
    _, meta = await client.json("https://example.org/h")
    assert len(meta["sha256"]) == 64 and meta["retrieved_at"].endswith("+00:00")
