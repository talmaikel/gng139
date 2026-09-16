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

from app.cities.herzliya.archive_facts import (CELL, MAX_SHORTLIST, TAG, enrich, facts,
                                               parse_requests)

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
    assert "strengthened" not in f and "occupied" not in f
    assert f["post_2005_permit"] is True
    assert f["permit_date"] == "1972-01-01"


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
    assert out["fetched"] == 1 and archive.read == ["1546", "7351"]
    rows = {r.field: r for r in (await session.execute(
        select(FieldEvidence).where(FieldEvidence.opportunity_id == opp.id))).scalars()}
    assert rows["post_2005_permit"].value is True
    assert "1546" in rows["post_2005_permit"].location and "7351" in rows["post_2005_permit"].location
    assert rows["permit_date"].value == "1972-01-01"
    assert "strengthened" not in rows and "occupied" not in rows
