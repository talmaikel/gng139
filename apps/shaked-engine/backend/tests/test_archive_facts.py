"""מה שעמוד תיק הבניין עונה עליו — ופרטיות בזמן הפרסור.

‏**W5 · 16.09.** הפיקסטורות כאן החזיקו ״תמא 38 - חיזוק״ בעמודה השלישית, כאילו
היא תיאור הבקשה. בעמוד האמיתי היא ״ארוע אחרון להצגה״, ושם כתוב ״מסירת היתר
למבקש״ — ולכן הבדיקות עברו והקוד היה עיוור. השורות כאן בנויות עכשיו כמו
העמוד: אותן עמודות, אותו סדר, ואותם נוסחי ארוע שנמצאו בתיקים.
"""
import re
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.cities.herzliya.archive_facts import (CELL, DETAIL_FROM_YEAR, MAX_REQUEST_PAGES,
                                               MAX_SHORTLIST, REQUEST_METHOD, TAG, enrich,
                                               facts, parse_request_page, parse_requests,
                                               request_facts)

# הכותרת כפי שהיא בעמוד GetTikFile (תיק 3892, נשמר ב-13.09).
HEADER = """<table class="table table-condensed"><thead><tr>
    <th class="th-results-header"></th>
    <th class="th-results-header" translatable-text>מספר בקשה</th>
    <th class="th-results-header" translatable-text>תאריך הגשה</th>
    <th class="th-results-header hidden-on-mobile" translatable-text>ארוע אחרון להצגה</th>
    <th class="th-results-header hidden-on-mobile" translatable-text>שם המבקש</th>
    <th class="th-results-header hidden-on-mobile" translatable-text>היתר</th>
    <th class="th-results-header hidden-on-mobile" translatable-text>תאריך היתר</th>
    <th class="th-results-header center-text" translatable-text>מסמכים</th>
</tr></thead><tbody>"""

ROW = """<tr>
    <td><a href="javascript:getRequest({req})"><span class="glyphicon glyphicon-modal-window"></span></a></td>
    <td><a href="javascript:getRequest({req})">{req}</a></td>
    <td>{sub}</td>
    <td class="hidden-on-mobile">{event}</td>
    <td class="hidden-on-mobile">{name}</td>
    <td class="hidden-on-mobile">{permit}</td>
    <td class="hidden-on-mobile">{pdate}</td>
    <td></td>
</tr>"""


def page(*rows):
    return HEADER + "".join(ROW.format(**r) for r in rows) + "</tbody></table>"


# נוסחי ארוע אמיתיים מהתיקים — לא תיאורי בקשה
PERMIT_1972 = dict(req="19720140", sub="10/08/1972", event="פתיחת בקשה להיתר",
                   name="ישראל ישראלי", permit="474", pdate="19/11/1972")
PERMIT_2017 = dict(req="20140655", sub="29/10/2014", event="מסירת היתר למבקש",
                   name="חברה יזמית בע\"מ", permit="20140655", pdate="08/06/2017")
LAWYER_2020 = dict(req="20201340", sub="07/12/2020", event='החלפת שם עו"ד מייצג',
                   name="פלוני אלמוני", permit="", pdate="")
TAMA_OPEN = dict(req="20190115", sub="05/02/2019", event='פתיחת בקשה לתיאום מקדים - תמ"א 38',
                 name="חברה יזמית בע\"מ", permit="", pdate="")


# ── דף הבקשה (GetBakashaFile), כפי שהוא: 20140655 באלוף יגאל אלון 6, 16.09 ──

def request_page(kind, desc, permit_date="", essence=("",), name="עו\"ד פלוני אלמוני"):
    rows = "".join(f'<tr><td class="title" translatable-text>{k}</td><td>{v}</td></tr>' for k, v in [
        ("מספר תיק בניין", '<a href="javascript:getBuilding(3892)">3892</a>'),
        ("מספר הבקשה ברישוי זמין", ""), ("סוג הבקשה", kind), ("שימוש עיקרי", "בית מגורים משותף"),
        ("תיאור הבקשה", desc), ("מספר היתר", "20140655" if permit_date else ""),
        ("תאריך הפקת היתר", permit_date), ("שטח עיקרי", "558.85")])
    mahut = "".join(f"<tr><td>\u200f{line}</td></tr>" for line in essence)
    return f"""<div class="row" id="info-main"><h3>מידע כללי</h3>
      <table class="table table-condensed" role="presentation"><tbody>{rows}</tbody></table></div>
      <div class="row" id="mahut"><h3>מהות הבקשה</h3><table><tbody>{mahut}</tbody></table></div>
      <div class="row" id="baaley-inyan"><span translatable-text>בעלי עניין</span>
      <table><thead><tr><th>סוג בעל עניין</th><th>שם בעל עניין</th></tr></thead>
      <tbody><tr><td>מבקש</td><td>כל בעלי הנכס באמצעות {name}</td></tr>
      <tr><td>עורך</td><td>{name}</td></tr></tbody></table></div>
      <div id="events"><table><tr><td>מסירת היתר למבקש</td><td>{name}</td></tr></table></div>"""


TAMA_PERMIT_PAGE = request_page('בקשה להיתר לתמ"א 38', 'תמ"א 38 - תוספת וחיזוק', "08/06/2017",
                                ("תכנית תוספות ושינויים להיתר מס' 20110552 לחיזוק ותוספת",
                                 "מבנה מגורים מדורג בן 5.5 קומות מכח תמ\"א 38"))
TAMA_OPEN_PAGE = request_page('בקשה לתיאום מקדים - תמ"א 38', 'תמ"א 38 - תוספת וחיזוק')
ADDITION_PERMIT_PAGE = request_page("בקשה להיתר", "תוספת בניה", "19/03/2013",
                                    ("סגירת מרפסת והרחבת דירה בקומה ב'",))
TASHRIT_PAGE = request_page("בקשה לרישום תשריט בית משותף", "תיקון תשריט בית משותף", "",
                            ("ביטול יחידה 271/19 (חדר אשפה) והחזרת שטחה לרכוש המשותף",
                             "בהתאם לתמ\"א 38."))


def test_the_header_is_the_order_the_parser_assumes():
    """אם העירייה תזיז עמודה, הבדיקה הזו נופלת — ולא הקוד שקורא אותה בשקט."""
    names = [TAG.sub("", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", HEADER, re.S)]
    assert names == ["", "מספר בקשה", "תאריך הגשה", "ארוע אחרון להצגה",
                     "שם המבקש", "היתר", "תאריך היתר", "מסמכים"]
    row = parse_requests(page(PERMIT_2017))[0]
    cells = [TAG.sub("", c).strip() for c in CELL.findall(ROW.format(**PERMIT_2017))]
    by_name = dict(zip(names, cells))
    assert row["req"] == int(by_name["מספר בקשה"])
    assert row["submitted"] == by_name["תאריך הגשה"]
    assert row["last_event"] == by_name["ארוע אחרון להצגה"]
    assert row["permit"] == by_name["היתר"]
    assert row["permit_date"] == by_name["תאריך היתר"]


def test_the_applicant_name_is_never_read():
    """העמודה מדולגת בפרסור, לא מסוננת אחר כך — שם שלא נקרא אינו נשמר בטעות."""
    rows = parse_requests(page(PERMIT_1972, PERMIT_2017, LAWYER_2020, TAMA_OPEN))
    blob = repr(rows) + repr(facts(rows))
    assert "ישראלי" not in blob and "חברה יזמית" not in blob and "אלמוני" not in blob
    assert set(rows[0]) == {"req", "submitted", "last_event", "permit", "permit_date"}


def test_the_last_event_is_not_read_as_strengthening():
    """אלוף יגאל אלון 6: היתר מ-2017 שהארוע האחרון שלו ״מסירת היתר למבקש״.
    הקוד הישן קבע ״לא חוזק״ ו״אין יוזמה״ — על עמודה שאינה אומרת את זה."""
    f = facts(parse_requests(page(PERMIT_1972, PERMIT_2017, LAWYER_2020)))
    assert "strengthened" not in f and "occupied" not in f      # רק דף הבקשה קובע
    assert f["post_2005_permit"] is True
    assert f["permit_date"] == "1972-01-01"


# ── דף הבקשה ──

def test_the_request_page_is_cut_before_the_interested_parties():
    """השמות יושבים ב״בעלי עניין״ ובאירועים, אחרי המהות. הדף נחתך שם בפרסור —
    לא מסונן אחר כך — ולכן שם אינו יכול להישמר בטעות."""
    d = parse_request_page(TAMA_PERMIT_PAGE)
    assert "פלוני" not in repr(d) and "אלמוני" not in repr(d)
    assert d["type"] == 'בקשה להיתר לתמ"א 38' and d["permit_date"] == "08/06/2017"
    assert set(d) == {"type", "description", "permit_date", "tama38", "mentions"}
    assert "essence" not in d                                  # המהות מזינה בוליאני בלבד


def test_a_tama38_request_with_a_permit_is_a_strengthening_under_section_70a():
    """אלוף יגאל אלון 6: עמוד התיק אמר ״מסירת היתר למבקש״; דף הבקשה אומר
    ״בקשה להיתר לתמ״א 38״ עם היתר מ-08/06/2017. זה §70א(2)."""
    rf = request_facts([{**parse_request_page(TAMA_PERMIT_PAGE), "req": 20140655}])
    assert rf["strengthened"] is True and rf["occupied"] is False
    assert rf["strengthening_permits"] == [(20140655, "08/06/2017")]
    assert rf["tama38_mention"] is True


def test_a_tama38_request_without_a_permit_is_another_developer_at_the_table():
    rf = request_facts([{**parse_request_page(TAMA_OPEN_PAGE), "req": 20190115}])
    assert rf["occupied"] is True and rf["strengthened"] is False
    assert rf["open_tama_requests"] == [20190115]


def test_an_ordinary_addition_permit_after_2005_is_neither():
    """היתר לסגירת מרפסת מ-2013 הוא היתר אחרי 2005 — אבל לא חיזוק ולא יוזמה."""
    rf = request_facts([parse_request_page(ADDITION_PERMIT_PAGE)])
    assert rf == {"strengthened": False, "occupied": False, "tama38_mention": False,
                  "strengthening_permits": [], "open_tama_requests": []}


def test_a_tashrit_that_mentions_tama38_feeds_the_renewal_hint_only():
    """הרצוג 3 (תיק 1546): תיקון תשריט ״בהתאם לתמ״א 38״ מעיד על בניין שכבר
    חודש — לא על בקשת חיזוק. הסיווג העירוני קובע את השערים; המהות רק מרמזת."""
    rf = request_facts([parse_request_page(TASHRIT_PAGE)])
    assert rf["strengthened"] is False and rf["occupied"] is False
    assert rf["tama38_mention"] is True


def test_a_partial_reading_says_yes_when_it_found_and_never_says_not_found():
    d = parse_request_page(ADDITION_PERMIT_PAGE)
    partial = request_facts([d], complete=False)
    assert partial["strengthened"] is None and partial["occupied"] is None
    assert request_facts([parse_request_page(TAMA_PERMIT_PAGE)], complete=False)["strengthened"] is True
    assert request_facts([], complete=True) == {"strengthened": False, "occupied": False,
                                                "tama38_mention": False,
                                                "strengthening_permits": [], "open_tama_requests": []}


def test_a_tama38_last_event_is_kept_as_a_positive_hint_only():
    """הר מירון 3 (תיק 475): ארוע שמזכיר תמ״א 38 הוא סימן אמיתי. היעדרו אינו."""
    assert facts(parse_requests(page(PERMIT_1972, TAMA_OPEN)))["tama38_event"] is True
    assert facts(parse_requests(page(PERMIT_1972, PERMIT_2017)))["tama38_event"] is False


def test_a_representative_in_a_last_event_is_a_boolean_and_nothing_more():
    f = facts(parse_requests(page(PERMIT_1972, LAWYER_2020)))
    assert f["representative_event"] is True
    assert facts(parse_requests(page(PERMIT_1972)))["representative_event"] is False
    assert all(not isinstance(v, str) or "פלוני" not in v for v in f.values())


def test_the_earliest_request_sets_the_permit_date():
    f = facts(parse_requests(page(PERMIT_2017, PERMIT_1972)))
    assert f["permit_date"] == "1972-01-01"


@pytest.mark.asyncio
async def test_enrich_refuses_to_become_a_sweep():
    """הארכיון עונה לפרצים ב-429. המודול מיועד לרשימה קצרה, והמגבלה אוכפת."""
    with pytest.raises(ValueError, match="סריקה"):
        await enrich(None, list(range(MAX_SHORTLIST + 1)))


def test_the_live_archive_path_also_answers_the_post_2005_exclusion():
    """‏`facts()` הוא מה ש-`enrich()` כותב על הזדמנות אמיתית. בלי השדה הזה
    המסלול החי היה מחזיר תקרת 400% מנופחת בעוד שהזורע המקומי לא."""
    after = dict(req="20060011", sub="01/01/2006", event="מסירת היתר למבקש",
                 name="פלוני", permit="7", pdate="19/05/2005")
    assert facts(parse_requests(page(PERMIT_1972)))["post_2005_permit"] is False
    assert facts(parse_requests(page(PERMIT_1972, after)))["post_2005_permit"] is True


def test_a_request_number_after_2005_is_not_itself_a_permit_after_2005():
    """מספר הבקשה נושא שנה, וקל להחליף בינו לבין מועד ההיתר. בקשה מ-2006
    שלא הופק לה היתר אינה מחריגה דבר."""
    open_2006 = dict(req="20060011", sub="01/01/2006", event="פתיחת בקשה להיתר",
                     name="פלוני", permit="", pdate="")
    assert facts(parse_requests(page(open_2006)))["post_2005_permit"] is False


class TwoFiles:
    """ארכיון מדומה: לחלקה שני תיקים, וההיתר שאחרי 2005 רק בשני."""
    def __init__(self):
        self.read = []

    async def find_tik_ids(self, block, parcel):
        return ["1546", "7351"]

    async def file(self, tik):
        self.read.append(tik)
        rows = (PERMIT_1972,) if tik == "1546" else (PERMIT_2017,)
        return {"html": page(*rows), "source": {
            "url": f"https://handasi.complot.co.il/x?t={tik}",
            "retrieved_at": datetime.now(timezone.utc).isoformat()}}

    async def request(self, req):
        self.read.append(f"req:{req}")
        return {"html": TAMA_PERMIT_PAGE, "source": {}}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_enrich_reads_every_building_file_of_the_parcel(session):
    """הרצוג 3 היא תיק 1546 **ו**-7351, ונקרא רק הראשון. היתר שיושב בשני
    לא נראה — וזה בדיוק ההיתר שמסמן חידוש."""
    from app.models.evidence import FieldEvidence
    from app.models.opportunity import Opportunity, VerificationLevel
    opp = Opportunity(city_code="herzliya", address="רחוב התיקים 1", block="9811", block_suffix=0,
                      parcel=str(uuid.uuid4().int % 1000), verification_level=VerificationLevel.RAW.value,
                      geom="SRID=4326;MULTIPOLYGON(((34.84 32.16,34.8404 32.16,34.8404 32.1603,"
                           "34.84 32.1603,34.84 32.16)))", metadata_json={})
    session.add(opp)
    await session.flush()
    archive = TwoFiles()

    out = await enrich(session, [opp.id], client=archive)
    # דפי הבקשה: רק 20140655 (מ-2005 ואילך). 19720140 אינו יכול להיות חיזוק מכוח תמ״א 38.
    assert out["fetched"] == 1 and archive.read == ["1546", "7351", "req:20140655"]
    rows = {r.field: r for r in (await session.execute(
        select(FieldEvidence).where(FieldEvidence.opportunity_id == opp.id))).scalars()}
    assert rows["post_2005_permit"].value is True
    assert "1546" in rows["post_2005_permit"].location and "7351" in rows["post_2005_permit"].location
    assert rows["permit_date"].value == "1972-01-01"
    assert rows["strengthened"].value is True and rows["occupied"].value is False
    assert rows["strengthened"].method == REQUEST_METHOD
    assert "20140655" in rows["strengthened"].location and "08/06/2017" in rows["strengthened"].location
    assert "פלוני" not in rows["strengthened"].location


class ManyRequests:
    """תיק אחד עם יותר בקשות מ-2005 ואילך מהתקרה, ובהן אחת ישנה."""
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    async def find_tik_ids(self, block, parcel):
        return ["1546"]

    async def file(self, tik):
        rows = [PERMIT_1972] + [dict(PERMIT_2017, req=str(20100000 + n), permit=str(20100000 + n))
                                for n in range(MAX_REQUEST_PAGES + 1)]
        return {"html": page(*rows), "source": {
            "url": "https://handasi.complot.co.il/x?t=1546",
            "retrieved_at": datetime.now(timezone.utc).isoformat()}}

    async def request(self, req):
        self.asked.append(int(req))
        return {"html": self.pages(req), "source": {}}

    async def close(self):
        pass


def _opp(session_add, block):
    from app.models.opportunity import Opportunity, VerificationLevel
    return Opportunity(city_code="herzliya", address=f"רחוב התקרה {block}", block=block, block_suffix=0,
                       parcel=str(uuid.uuid4().int % 100000), verification_level=VerificationLevel.RAW.value,
                       geom="SRID=4326;MULTIPOLYGON(((34.84 32.16,34.8404 32.16,34.8404 32.1603,"
                            "34.84 32.1603,34.84 32.16)))", metadata_json={})


@pytest.mark.asyncio
async def test_over_the_cap_a_blind_row_is_removed_and_nothing_false_is_written(session):
    """‏15 דפי בקשה בקצב של 10 שניות הם הגבול. מעבר לו — מה שנמצא נכתב,
    ״לא נמצא״ לא נכתב, והשורה העיוורת מהקריאה של W5 נמחקת בכל מקרה."""
    from app.models.evidence import FieldEvidence
    opp = _opp(session.add, "9813")
    session.add(opp)
    await session.flush()
    session.add(FieldEvidence(opportunity_id=opp.id, field="strengthened", value=False,
                              certainty="derived", source_url="https://handasi.complot.co.il/old",
                              retrieved_at=datetime.now(timezone.utc), location="תיק 1546",
                              method="שורות הבקשות בתיק הבניין; שם המבקש אינו נקרא"))
    await session.flush()
    archive = ManyRequests(lambda req: ADDITION_PERMIT_PAGE)

    await enrich(session, [opp.id], client=archive)
    assert len(archive.asked) == MAX_REQUEST_PAGES and 19720140 not in archive.asked
    assert all(n >= DETAIL_FROM_YEAR * 10000 for n in archive.asked)
    rows = {r.field: r for r in (await session.execute(
        select(FieldEvidence).where(FieldEvidence.opportunity_id == opp.id))).scalars()}
    assert "strengthened" not in rows and "occupied" not in rows       # לא ידוע, ולא ״לא״

    archive = ManyRequests(lambda req: TAMA_OPEN_PAGE if req.endswith("3") else ADDITION_PERMIT_PAGE)
    await enrich(session, [opp.id], client=archive)
    rows = {r.field: r for r in (await session.execute(
        select(FieldEvidence).where(FieldEvidence.opportunity_id == opp.id))).scalars()}
    assert rows["occupied"].value is True and "strengthened" not in rows


class Refusing:
    """ארכיון שמסרב מהתיק הראשון."""
    def __init__(self):
        self.files = 0

    async def find_tik_ids(self, block, parcel):
        return ["1546"]

    async def file(self, tik):
        from app.cities.herzliya.archive_client import ArchiveBlocked
        self.files += 1
        raise ArchiveBlocked("verification page")

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_a_refusal_stops_the_list_and_counts_as_failed_not_empty(session):
    """סירוב אינו ״תיק ריק״: ריק הופך למסירה שמדלגת על החלקה, ונכשל — ל״נסה שוב״."""
    from app.models.opportunity import Opportunity, VerificationLevel
    ids = []
    for n in range(3):
        opp = Opportunity(city_code="herzliya", address=f"רחוב הסירוב {n}", block="9812", block_suffix=0,
                          parcel=str(uuid.uuid4().int % 100000), verification_level=VerificationLevel.RAW.value,
                          geom="SRID=4326;MULTIPOLYGON(((34.84 32.16,34.8404 32.16,34.8404 32.1603,"
                               "34.84 32.1603,34.84 32.16)))", metadata_json={})
        session.add(opp)
        await session.flush()
        ids.append(opp.id)
    archive = Refusing()

    out = await enrich(session, ids, client=archive)
    assert archive.files == 1, "אחרי סירוב אין פונים שוב"
    assert out["blocked"] is True and out["failed"] == 3 and out["empty"] == 0
