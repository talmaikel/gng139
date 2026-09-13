"""שני השערים שרק הארכיון עונה עליהם — ופרטיות בזמן הפרסור."""
import pytest

from app.cities.herzliya.archive_facts import MAX_SHORTLIST, facts, parse_requests

ROW = ('<tr><td>1</td><td>{req}</td><td>{sub}</td><td>{act}</td>'
       '<td>{name}</td><td>{permit}</td><td>{pdate}</td></tr>')


def page(*rows):
    return "".join(ROW.format(**r) for r in rows)


PERMIT_1978 = dict(req="19780028", sub="12/03/1978", act="פתיחת בקשה להיתר",
                   name="ישראל ישראלי", permit="1234", pdate="23/07/1978")
TAMA_OPEN = dict(req="20190115", sub="01/01/2019", act='פתיחת בקשה לתיאום מקדים - תמ"א 38',
                 name="חברה יזמית בע\"מ", permit="", pdate="")
TAMA_PERMITTED = dict(req="20140055", sub="01/01/2014", act="תמא 38 - חיזוק",
                      name="פלוני", permit="9999", pdate="01/06/2015")


def test_the_applicant_name_is_never_read():
    """העמודה מדולגת בפרסור, לא מסוננת אחר כך — שם שלא נקרא אינו נשמר בטעות."""
    rows = parse_requests(page(PERMIT_1978, TAMA_OPEN))
    blob = repr(rows)
    assert "ישראלי" not in blob and "חברה יזמית" not in blob
    assert set(rows[0]) == {"req", "submitted", "action", "permit", "permit_date"}


def test_strengthening_with_a_permit_disqualifies_under_70a2():
    f = facts(parse_requests(page(PERMIT_1978, TAMA_PERMITTED)))
    assert f["strengthened"] is True
    assert f["occupied"] is False        # הגיע להיתר — לא "יזם שעובד עליו", אלא פסול


def test_strengthening_without_a_permit_means_someone_else_is_already_there():
    f = facts(parse_requests(page(PERMIT_1978, TAMA_OPEN)))
    assert f["occupied"] is True
    assert f["strengthened"] is False    # שני דברים שונים, ולא אותו שער


def test_a_clean_file_is_neither():
    f = facts(parse_requests(page(PERMIT_1978)))
    assert (f["strengthened"], f["occupied"]) == (False, False)
    assert f["permit_date"] == "1978-01-01"


def test_the_earliest_request_sets_the_permit_date():
    f = facts(parse_requests(page(TAMA_PERMITTED, PERMIT_1978)))
    assert f["permit_date"] == "1978-01-01"


@pytest.mark.asyncio
async def test_enrich_refuses_to_become_a_sweep():
    """הארכיון עונה לפרצים ב-429. המודול מיועד לרשימה קצרה, והמגבלה אוכפת."""
    from app.cities.herzliya.archive_facts import enrich
    with pytest.raises(ValueError, match="סריקה"):
        await enrich(None, list(range(MAX_SHORTLIST + 1)))


def test_the_live_archive_path_also_answers_the_post_2005_exclusion():
    """‏`facts()` הוא מה ש-`enrich()` כותב על הזדמנות אמיתית. בלי השדה הזה
    המסלול החי היה מחזיר תקרת 400% מנופחת בעוד שהזורע המקומי לא."""
    after = dict(req="20060011", sub="01/01/2006", act="תוספת בנייה",
                 name="פלוני", permit="7", pdate="19/05/2005")
    assert facts(parse_requests(page(PERMIT_1978)))["post_2005_permit"] is False
    assert facts(parse_requests(page(PERMIT_1978, after)))["post_2005_permit"] is True


def test_a_request_number_after_2005_is_not_itself_a_permit_after_2005():
    """מספר הבקשה נושא שנה, וקל להחליף בינו לבין מועד ההיתר. בקשה מ-2006
    שלא הופק לה היתר אינה מחריגה דבר."""
    open_2006 = dict(req="20060011", sub="01/01/2006", act="תוספת בנייה",
                     name="פלוני", permit="", pdate="")
    assert facts(parse_requests(page(open_2006)))["post_2005_permit"] is False
