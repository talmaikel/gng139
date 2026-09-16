import httpx
import pytest

from app.cities.herzliya.archive_client import ArchiveDocument, HerzliyaArchiveClient, HerzliyaArchiveError
from app.sources.client import AsyncPublicClient
from tests.conftest import no_wait

# המודול הזה בודק את הלקוח עצמו, עם transport מדומה משלו, ולכן הוא
# פטור מהשומר שאוסר על הסוויטה לפנות לארכיון.
pytestmark = pytest.mark.archive_client

FOUND = "<a href=\"#building/1652\">1652</a> <script>getBuilding('1653')</script>"
NO_RESULTS = "<div>ERR_NO_RESULTS</div>"
UNRECOGNISED = "<html>maintenance</html>"


def archive(tmp_path, handler):
    public = AsyncPublicClient(tmp_path, transport=httpx.MockTransport(handler), sleep=no_wait)
    return HerzliyaArchiveClient(public_client=public)


def page(body):
    return lambda request: httpx.Response(200, text=body)


async def test_a_search_tells_no_results_apart_from_an_unrecognised_page(tmp_path):
    for expected, body in [("found", FOUND), ("empty", NO_RESULTS), ("unrecognized", UNRECOGNISED)]:
        result = await archive(tmp_path / expected, page(body)).search("6424", "83")
        assert result.status == expected
    assert (await archive(tmp_path / "ids", page(FOUND)).search("6424", "83")).tik_ids == ["1652", "1653"]


async def test_find_tik_ids_will_not_read_an_unrecognised_page_as_no_files(tmp_path):
    with pytest.raises(HerzliyaArchiveError, match="Unrecognised"):
        await archive(tmp_path / "odd", page(UNRECOGNISED)).find_tik_ids("6424", "83")
    assert await archive(tmp_path / "none", page("לא נמצאו תיקים")).find_tik_ids("6424", "83") == []


async def test_an_address_search_checks_the_count_the_page_declares(tmp_path):
    short = "<p>נמצאו 3 תיקי בניין</p><a href='#building/1'></a><a href='#building/2'></a>"
    with pytest.raises(HerzliyaArchiveError, match="declared 3, parsed 2"):
        await archive(tmp_path / "short", page(short)).search_address("123")
    complete = "<p>נמצאו 2 תיקי בניין</p><a href='#building/1'></a><a href='#building/2'></a>"
    result = await archive(tmp_path / "complete", page(complete)).search_address("123")
    assert result["tik_ids"] == ["1", "2"] and result["declared_count"] == 2


async def test_download_refuses_an_untrusted_host_before_any_request(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b"%PDF-1.4")

    client = archive(tmp_path, handler)
    with pytest.raises(HerzliyaArchiveError, match="untrusted"):
        await client.download(ArchiveDocument(tik_id="1", url="https://evil.example.com/permit.pdf"))
    assert calls == []
    assert await client.download(ArchiveDocument(tik_id="1", url="https://archive.gis-net.co.il/Herzeliya/p.pdf")) == b"%PDF-1.4"


async def test_streets_keep_herzliya_only_and_drop_duplicates(tmp_path):
    body = {
        "d": [
            {"k": "6400", "v": "10", "label": "הרצל"},
            {"k": "6400", "v": "10", "label": "הרצל"},
            {"k": "6600", "v": "11", "label": "רחוב בעיר אחרת"},
            {"k": "6400", "v": "x", "label": "קוד לא מספרי"},
        ]
    }
    result = await archive(tmp_path, lambda r: httpx.Response(200, json=body)).streets()
    assert result["streets"] == [{"code": "10", "name": "הרצל"}] and result["source"]["method"] == "POST"


async def test_find_documents_keeps_pdf_links_and_resolves_relative_ones(tmp_path):
    links = '<a href="/files/a.pdf">a</a><a href="x.html">x</a><a href="https://archive.gis-net.co.il/b.PDF">b</a>'
    documents = await archive(tmp_path, page(links)).find_documents("1652")
    assert [d.url for d in documents] == ["https://handasi.complot.co.il/files/a.pdf", "https://archive.gis-net.co.il/b.PDF"]
    assert {d.tik_id for d in documents} == {"1652"}


# ‏16.09 · שני העמודים כפי שהארכיון החזיר אותם אחרי פרץ בקשות — ב-200.
CAPTCHA = "<h2>אימות משתמש</h2><p>נדרש אימות משתמש</p><div class='g-recaptcha'></div>"
REFUSED = "<p>מצטערים, לא ניתן להציג את המידע המבוקש. לא אותרו תוצאות התואמות את מאפייני החיפוש שהוגדרו</p>"


async def test_a_refusal_page_raises_and_is_not_kept_in_the_cache(tmp_path):
    """65 תיקים ״ריקים״ ברצף היו סירוב, והסירוב נשמר במטמון ליממה."""
    from app.cities.herzliya.archive_client import ArchiveBlocked
    answers = [REFUSED, CAPTCHA, "<table><tr><td>20170371</td></tr></table>"]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=answers[len(calls) - 1])

    client = archive(tmp_path, handler)
    for _ in range(2):
        with pytest.raises(ArchiveBlocked):
            await client.file("8817")
    assert "20170371" in (await client.file("8817"))["html"]
    assert len(calls) == 3
