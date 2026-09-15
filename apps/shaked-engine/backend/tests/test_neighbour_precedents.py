"""פרויקטים באותו רחוב — מעמודים שנרשמו מהארכיון, בלי רשת.

הקבצים ב-`tests/fixtures/complot/` נשלפו ב-14.09.2026 (ראו README שם).
שמות בעלי עניין ומבקשים הוחלפו בשמות בדויים — **והבדיקות מוודאות שגם
הבדויים אינם נקראים**, כי שם שנקרא הוא שם שיכול להישמר.
"""
import inspect
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.cities.herzliya import neighbour_precedents as n
from app.cities.herzliya import rights, rules
from app.cities.herzliya.archive_client import ArchiveBlocked, HerzliyaArchiveClient, assert_archive_page
from app.cities.herzliya.dossier import _precedents
from app.sources.client import AsyncPublicClient
from tests.conftest import no_wait

FIXTURES = Path(__file__).parent / "fixtures" / "complot"
PLANTED_NAMES = ("ישראל ישראלי", "חברה לדוגמה", "אדריכל לדוגמה", "מהנדס לדוגמה", "בודק לדוגמה", "בעלים לדוגמה")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _no_names(obj) -> None:
    blob = repr(obj)
    for name in PLANTED_NAMES:
        assert name not in blob, name


# ── הרחוב הקובע ──

def test_the_narrow_frontage_names_the_governing_street():
    loc = ("גוש 6537 חלקה 221 · 12.0 מ׳ residential (מוהליבר) · 37.9 מ׳ residential (הנוטרים) "
           "· 21.8 מ׳ tertiary → הצרה קובעת 12.0")
    assert n.governing_street(loc) == "מוהליבר"


@pytest.mark.parametrize("loc", [
    "12.0 מ׳ residential (א) · 12.0 מ׳ residential (ב) → הצרה קובעת 12.0",   # שני שמות באותו רוחב
    "21.8 מ׳ tertiary · 30.0 מ׳ residential (ב) → הצרה קובעת 21.8",          # החזית הקובעת בלי שם
    "קו רחוב סמוך אך הרוחב לא נמדד — ייתכן כביש צמוד",
    None,
])
def test_no_governing_street_is_guessed(loc):
    assert n.governing_street(loc) is None


CATALOGUE = [{"code": "324", "name": "סנש חנה"}, {"code": "506", "name": "י.ל.ברוך"},
             {"code": "862", "name": "קמין ברוך"}, {"code": "101", "name": "אלוף יגאל אלון"},
             {"code": "456", "name": "הנוטרים"}]


@pytest.mark.parametrize("osm_name, code", [
    ("חנה סנש", "324"), ("י.ל. ברוך", "506"), ("יגאל אלון", "101"), ("הנוטרים", "456"),
    ("ברוך", None),          # שני רחובות — לא בוחרים
    ("הרצל", None),
])
def test_the_street_code_is_matched_unambiguously_or_not_at_all(osm_name, code):
    assert n.match_street(osm_name, CATALOGUE) == code


# ── רשימת הבקשות ──

def test_the_request_list_is_read_by_column_without_the_applicant():
    out = n.parse_request_list(fixture("requests_by_address_t22_hanotrim.html"))
    assert out["status"] == "found" and out["declared"] == 4 and out["complete"]
    assert [(r["request"], r["tik"], r["house_number"], r["gush"], r["helka"]) for r in out["rows"]] == [
        (20130622, 3704, 10, "6537", "181"), (20140997, 3699, 2, "6537", "133"),
        (20150432, 3699, 2, "6537", "133"), (20161092, 3704, 10, "6537", "181")]
    assert set(out["rows"][0]) == {"request", "tik", "address", "street", "house_number", "gush", "helka"}
    _no_names(out)


def test_an_empty_request_list_is_empty_and_not_unrecognised():
    out = n.parse_request_list(fixture("requests_by_address_no_results.html"))
    assert (out["status"], out["rows"]) == ("empty", [])
    assert n.parse_request_list("<html>maintenance</html>")["status"] == "unrecognized"


# ── עמוד הבקשה ──

def test_a_tama38_request_yields_the_total_and_not_the_existing_or_the_addition():
    """המהות אומרת ״בן 3 קומות... 12 יחי"ד״ (הקיים), ״תוספת 2.5 קומות, 6 יחי"דיור״
    (התוספת) ו״סה"כ 6.5 קומות... סה"כ 18 יחי"דיור״ (הבניין). רק האחרון נקרא."""
    req = n.parse_request_page(fixture("request_20130622_tama38_totals.html"))
    assert req["request_type"] == 'בקשה להיתר לתמ"א 38'
    assert (req["permit"], req["permit_date"], req["address"]) == ("20130622", "2015-11-11", "הנוטרים 10")
    assert req["units_requested"] == 6                     # התוספת — נשמרת בנפרד, אינה ״יחידות״
    kind = n.classify(req)
    assert kind == "tama38_1"
    blob = f'{req["description"]} {req["essence"]}'
    assert n.parse_floors(blob, kind) == {"value": 6.5, "quote": 'סה"כ 6.5 קומות'}
    assert n.parse_units(blob, kind)["value"] == 18
    _no_names(req)


def test_a_description_without_floors_is_not_stated_never_guessed():
    req = n.parse_request_page(fixture("request_20161092_tama38_no_floors.html"))
    kind = n.classify(req)
    assert kind == "tama38_1" and req["permit_date"] == "2019-02-20"
    blob = f'{req["description"]} {req["essence"]}'
    assert n.parse_floors(blob, kind) == {"value": None, "quote": None, "note": "לא צוין"}
    assert n.parse_units(blob, kind)["value"] is None
    _no_names(req)


def test_an_addition_to_an_existing_building_is_not_a_renewal_precedent():
    """מעלית לבית ״בן 3 קומות על עמודים, 6 יחי"דיור״ — הריסת מדרגות אינה הריסת בניין."""
    req = n.parse_request_page(fixture("request_20130304_elevator_existing_building.html"))
    assert n.classify(req) is None
    assert n.parse_floors(f'{req["description"]} {req["essence"]}', None)["value"] is None
    _no_names(req)


@pytest.mark.parametrize("text, kind, floors, units", [
    ('הריסת בניין קיים והקמת בניין חדש בן 11.5 קומות כולל ק.קרקע מעל 2 קומות מרתף, 42 יח"ד',
     "tama38_2", 11.5, 42),
    ("תוספת 2.5 קומות לבניין בן 4 קומות", "tama38_1", None, None),            # רק תוספת וקיים
    ("בניין בן 7 קומות כולל קומת קרקע", "tama38_1", None, None),              # ״בן״ — הקיים
    ('סה"כ 8 קומות ... סה"כ 9 קומות', "tama38_2", None, None),                # סתירה
    ('תוספת 12 יח"ד לבניין קיים בן 16 יח"ד', "tama38_1", None, None),          # יח״ד בלי סכום
])
def test_the_floor_parser_is_conservative(text, kind, floors, units):
    assert n.parse_floors(text, kind)["value"] == floors
    assert n.parse_units(text, kind)["value"] == units


def test_classification_reads_only_explicit_words():
    assert n.classify({"request_type": "בקשה להיתר", "essence": "הריסת הבניין הקיים והקמת בניין מגורים חדש"}) == "new_build"
    assert n.classify({"request_type": 'בקשה להיתר לתמ"א 38', "essence": "הריסה ובנייה"}) == "tama38_2"
    assert n.classify({"request_type": "בקשה להיתר", "essence": "חלופת שקד — הריסה ובנייה"}) == "shaked"
    assert n.classify({"request_type": "בקשה להיתר", "essence": "סגירת מרפסת"}) is None


# ── עצירה ──

@pytest.mark.parametrize("name", ["captcha.html", "soft_block.html"])
def test_a_captcha_or_soft_block_page_is_a_stop_signal(name):
    with pytest.raises(ArchiveBlocked):
        assert_archive_page(fixture(name), "test")


def test_the_soft_block_sentence_inside_a_real_page_is_not_a_block():
    assert_archive_page("<div>" + "x" * 5000 + "לא ניתן להציג את המידע המבוקש</div>", "test")


# ── האיסוף, מול ארכיון מדומה ──

def _archive(tmp_path, pages: dict, calls: list):
    def handler(request: httpx.Request):
        q = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        calls.append(q)
        key = (q["prgname"], q.get("t") or q.get("b"))
        return httpx.Response(200, text=pages[key]() if callable(pages[key]) else pages[key])
    public = AsyncPublicClient(tmp_path, transport=httpx.MockTransport(handler), sleep=no_wait)
    return HerzliyaArchiveClient(public_client=public)


def _street_pages(overrides=None):
    pages = {
        ("GetBakashotByAddress", "22"): fixture("requests_by_address_t22_hanotrim.html"),
        ("GetBakashotByAddress", "1"): fixture("requests_by_address_no_results.html"),
        ("GetBakashaFile", "20130622"): fixture("request_20130622_tama38_totals.html"),
        ("GetBakashaFile", "20161092"): fixture("request_20161092_tama38_no_floors.html"),
        ("GetBakashaFile", "20140997"): fixture("request_20130304_elevator_existing_building.html"),
        ("GetBakashaFile", "20150432"): fixture("request_20130304_elevator_existing_building.html"),
    }
    return {**pages, **(overrides or {})}


@pytest.mark.archive_client
async def test_collect_finds_the_project_with_its_source_and_stays_in_budget(tmp_path):
    calls = []
    out = await n.collect(_archive(tmp_path, _street_pages(), calls), "456", anchor=6, own_parcel=None)
    assert out["status"] == "found"
    [p] = out["projects"]
    assert (p["address"], p["kind"], p["floors"], p["units"], p["permit_year"], p["request"], p["tik"]) == \
        ("הנוטרים 10", "tama38_1", 6.5, 18, 2015, 20130622, 3704)
    assert p["house_number_gap"] == 4
    assert "b=20130622" in p["source_url"] and p["retrieved_at"]
    # שני עמודי רשימה + לכל היותר MAX_REQUEST_PAGES עמודי בקשה. תכנית השינויים
    # של אותו תיק (20161092) אינה נשלפת: לתיק כבר יש פרויקט.
    pages = [c for c in calls if c["prgname"] == "GetBakashaFile"]
    assert len(calls) - len(pages) == 2 and len(pages) <= n.MAX_REQUEST_PAGES
    assert "20161092" not in {c["b"] for c in pages}
    _no_names(out)


@pytest.mark.archive_client
async def test_the_budget_stops_the_fetching_and_says_so(tmp_path):
    calls = []
    out = await n.collect(_archive(tmp_path, _street_pages(), calls), "456", anchor=2, own_parcel=None,
                          max_pages=1)
    assert out["status"] == "budget_reached"
    assert len([c for c in calls if c["prgname"] == "GetBakashaFile"]) == 1


@pytest.mark.archive_client
async def test_the_clients_own_parcel_is_not_its_own_precedent(tmp_path):
    calls = []
    out = await n.collect(_archive(tmp_path, _street_pages(), calls), "456", anchor=10,
                          own_parcel=("6537", "181"))
    assert all(p["tik"] != 3704 for p in out["projects"])
    assert "20130622" not in {c.get("b") for c in calls}


@pytest.mark.archive_client
async def test_without_an_anchor_no_request_page_is_fetched(tmp_path):
    calls = []
    out = await n.collect(_archive(tmp_path, _street_pages(), calls), "456", anchor=None,
                          own_parcel=("6537", "999"))
    assert out["status"] == "no_anchor" and out["projects"] == []
    assert {c["prgname"] for c in calls} == {"GetBakashotByAddress"}


@pytest.mark.archive_client
@pytest.mark.parametrize("block", ["captcha.html", "soft_block.html"])
async def test_a_block_mid_way_stops_everything_and_returns_nothing(tmp_path, block):
    calls = []
    pages = _street_pages({("GetBakashaFile", "20130622"): fixture(block)})
    with pytest.raises(ArchiveBlocked):
        await n.collect(_archive(tmp_path, pages, calls), "456", anchor=6, own_parcel=None)
    assert calls[-1].get("b") == "20130622"              # עצר מיד, בלי לנסות את התיק הבא


@pytest.mark.archive_client
async def test_a_captcha_is_not_cached_as_the_page(tmp_path):
    """עמוד CAPTCHA מגיע ב-HTTP 200. בלי ניקוי הוא היה מוגש מהמטמון יום שלם."""
    answers = iter([fixture("captcha.html"), fixture("request_20130622_tama38_totals.html")])
    calls = []
    client = _archive(tmp_path, {("GetBakashaFile", "20130622"): lambda: next(answers)}, calls)
    with pytest.raises(ArchiveBlocked):
        await client.request_page(20130622)
    page, _ = await client.request_page(20130622)
    assert "סה\"כ 6.5 קומות" in page and len(calls) == 2


# ── התיק ──

def test_the_dossier_section_says_not_checked_rather_than_nothing():
    out = _precedents(None)
    assert out["status"] == "not_checked" and out["rows"] == [] and out["title"] == "פרויקטים באותו רחוב"


def test_the_dossier_rows_print_not_stated_and_carry_the_source():
    value = {"status": "found", "status_label": "נבדק", "street": {"name": "הנוטרים", "code": "456"},
             "projects": [{"address": "הנוטרים 10", "kind_label": n.KIND_LABEL["tama38_1"], "floors": None,
                           "units": 18, "permit_year": 2019, "house_number_gap": 4, "distance_m": 61,
                           "request": 20161092, "tik": 3704, "source_url": "https://handasi.complot.co.il/x?b=20161092"}]}
    field = {"value": value, "source": {"url": "https://handasi.complot.co.il/list", "retrieved_at": "2026-09-14T16:14:52+00:00"}}
    [row] = _precedents(field)["rows"]
    assert row["floors"] == "לא צוין" and row["units"] == "18" and row["permit_year"] == "2019"
    assert row["distance"] == "61 מ׳ · 4 מספרי בית"
    assert row["source"] == "בקשה 20161092 · תיק 3704" and row["source_url"].endswith("b=20161092")


def test_precedents_never_reach_the_floors_rule():
    """תקדים אינו כלל. אם מישהו יחבר את השדה לשערים — כאן זה ייפול."""
    assert n.FIELD not in rights.THRESHOLD_IDS
    assert n.FIELD not in inspect.getsource(rights) and n.FIELD not in inspect.getsource(rules)


def test_the_exports_render_the_section():
    from app.cities.herzliya import exports
    from tests.test_exports import _with_economics
    d = _with_economics()
    field = {"value": {"status": "found", "street": {"name": "הנוטרים"}, "projects": [
        {"address": "הנוטרים 10", "kind_label": n.KIND_LABEL["tama38_1"], "floors": 6.5, "floors_quote": 'סה"כ 6.5 קומות',
         "units": 18, "permit_year": 2015, "house_number_gap": 4, "request": 20130622, "tik": 3704}]},
             "source": {"url": "https://handasi.complot.co.il/list", "retrieved_at": "2026-09-14T16:14:52+00:00"}}
    d["neighbour_precedents"] = _precedents(field)
    assert exports.excel(d)[:2] == b"PK"
    try:
        assert exports.pdf(d)[:4] == b"%PDF"
    except RuntimeError as exc:                         # גופן עברי חסר במכונה — שגיאת התקנה
        pytest.skip(str(exc))


# ── מקצה לקצה, על מסד (מדלג כשאין מסד בדיקות) ──

class _RecordedArchive:
    """אותו ממשק כמו HerzliyaArchiveClient, מהעמודים שנרשמו."""

    def __init__(self):
        from datetime import datetime, timezone
        self.calls = []
        self.pages = _street_pages()
        self.stamp = datetime.now(timezone.utc).isoformat()   # ״נשלף עכשיו״, כדי שחלון הרעננות לא יתיישן בבדיקה

    async def streets(self):
        self.calls.append("GetStreets")
        return {"streets": CATALOGUE, "source": {}}

    async def requests_by_address(self, street_code, request_type):
        self.calls.append(("GetBakashotByAddress", str(request_type)))
        url = f"https://handasi.complot.co.il/magicscripts/mgrqispi.dll?prgname=GetBakashotByAddress&s={street_code}&t={request_type}"
        return self.pages[("GetBakashotByAddress", str(request_type))], {"url": url, "retrieved_at": self.stamp}

    async def request_page(self, request_no):
        self.calls.append(("GetBakashaFile", str(request_no)))
        url = f"https://handasi.complot.co.il/magicscripts/mgrqispi.dll?prgname=GetBakashaFile&b={request_no}"
        return self.pages[("GetBakashaFile", str(request_no))], {"url": url, "retrieved_at": self.stamp}


@pytest.mark.asyncio
async def test_the_dossier_shows_the_precedents_and_the_rights_do_not_move(session):
    from datetime import datetime, timezone

    from sqlalchemy import delete

    from app.cities.herzliya.dossier import build
    from app.cities.herzliya.rules import HerzliyaCityRules
    from app.evidence import Certainty
    from app.models.evidence import FieldEvidence
    from app.models.opportunity import Opportunity, VerificationLevel
    from tests.test_dossier import READY, SQUARE, _delivered

    c, _, opp = await _delivered(session, block="9702")
    opp.address = "הנוטרים 6"
    await session.execute(delete(FieldEvidence).where(
        FieldEvidence.opportunity_id == opp.id, FieldEvidence.field == "street_width"))
    session.add(FieldEvidence(
        opportunity_id=opp.id, field="street_width", value=READY["street_width"],
        certainty=Certainty.DERIVED.value, source_url="https://example.test/x",
        retrieved_at=datetime.now(timezone.utc),
        location="גוש 9702 חלקה 1 · 12.0 מ׳ residential (הנוטרים) → הצרה קובעת 12.0"))
    # השכן כבר במסד, ולכן יש לו מרחק במטרים.
    session.add(Opportunity(city_code="herzliya", address="הנוטרים 10", block="6537", block_suffix=0,
                            parcel="181", geom=f"SRID=4326;{SQUARE}", area_sqm=900.0,
                            verification_level=VerificationLevel.RAW.value, metadata_json={}))
    await session.flush()
    before = await HerzliyaCityRules().assess(session, opp.id)

    archive = _RecordedArchive()
    out = await n.fetch_for_dossier(session, opp.id, archive)
    assert out["status"] == "found" and out["street"] == {"name": "הנוטרים", "code": "456"}
    assert out["projects"][0]["distance_m"] is not None

    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    [row] = d["neighbour_precedents"]["rows"]
    assert (row["address"], row["floors"], row["units"], row["permit_year"]) == ("הנוטרים 10", "6.5", "18", "2015")
    assert n.FIELD not in {r["field"] for r in d["evidence"]}
    assert d["rights"]["floors"] == before["floors"] and d["rights"]["checks"] == before["checks"]
    _no_names(d["neighbour_precedents"])

    # שליפה שנעשתה נשמרת: קריאה שנייה אינה פונה לארכיון.
    calls = len(archive.calls)
    assert (await n.fetch_for_dossier(session, opp.id, archive))["from_cache"] is True
    assert len(archive.calls) == calls
