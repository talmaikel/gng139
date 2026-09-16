"""‏W4 · מילון המונחים — ה״?״ במסך, גיליון ״מונחים״ באקסל ונספח ה-PDF.

שלושה דברים יכולים להישבר כאן בשקט, ולכן שלושה סוגי בדיקות:

- **״?״ שנפתח ריק.** המסך מבקש מונח לפי מזהה. מזהה שאינו במילון אינו
  שגיאה בדפדפן — הסימן פשוט לא מופיע, ואיש לא שם לב. הרשימה של המסך
  (`TERM_IDS` ב-`frontend/src/lib/api.ts`) נקראת כאן ונבדקת מול השרת.
- **הסבר שמשקר.** מספר שכתוב במילון ביד (10,000 ₪, 30 יום) נבדק מול הקוד,
  כדי שההסבר לא יישאר מאחור כשהכלל זז. וגם ״מכריע״ עצמו: המסך מסביר ארבעה
  תנאים, והשרת צריך לחשב את ארבעתם.
- **משטח שלא קיבל את המילון.** האקסל וה-PDF נקראים חזרה.
"""
import io
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.cities.herzliya import exports, rights
from app.cities.herzliya.dossier import (
    CERTAINTY_LABEL, FIELD_LABEL, MARGINAL_LAND_VALUE_ILS, _evidence_rows, build,
)
from app.cities.herzliya.glossary import FIELD_TERM, GLOSSARY, glossary
from app.cities.herzliya.rules import HerzliyaCityRules
from app.core.config import get_settings
from app.services.economic.assumptions import get_assumptions
from tests.test_labels import IDENTIFIER

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
DOSSIER_PAGE = FRONTEND / "app" / "app" / "dossier" / "[id]" / "page.tsx"


def _frontend_term_ids() -> set[str]:
    """המזהים שהמסך מבקש, מתוך `TERM_IDS` — הרשימה ש-tsc אוכף על כל ״?״ במסך."""
    source = (FRONTEND / "lib" / "api.ts").read_text(encoding="utf-8")
    block = re.search(r"export const TERM_IDS = \[(.*?)\] as const", source, re.S)
    assert block, "לא נמצאה TERM_IDS ב-api.ts — הבדיקה הזו כבר אינה בודקת דבר"
    return set(re.findall(r'"([a-z0-9_]+)"', block.group(1)))


# ── המסך מבקש רק מה שקיים ──

def test_every_term_the_screen_asks_for_exists_on_the_server():
    ids = _frontend_term_ids()
    assert len(ids) >= 10, ids
    missing = sorted(ids - set(GLOSSARY))
    assert not missing, f"״?״ שייפתח ריק במסך: {missing}"


def test_the_dossier_page_uses_only_terms_from_the_list():
    """tsc אוכף את זה כבר. כאן מוודאים שהבדיקה שלמעלה קוראת את מה שבאמת בשימוש."""
    page = DOSSIER_PAGE.read_text(encoding="utf-8")
    used = set(re.findall(r'<(?:Term|WithTerm) id="([a-z0-9_]+)"', page))
    assert {"shaked_conditions", "deciding", "certainty", "cap_400", "profit_on_cost",
            "developer_area", "levy_ceiling", "levy_estimate", "levy_category"} <= used, used
    assert used <= _frontend_term_ids(), sorted(used - _frontend_term_ids())


def test_every_evidence_field_term_exists_and_the_screen_knows_it():
    assert set(FIELD_TERM) <= set(FIELD_LABEL)
    assert set(FIELD_TERM.values()) <= set(GLOSSARY)
    assert set(FIELD_TERM.values()) <= _frontend_term_ids()


# ── הנוסח עצמו ──

@pytest.mark.parametrize("term_id", list(GLOSSARY))
def test_an_entry_is_plain_hebrew_without_code_identifiers(term_id):
    entry = GLOSSARY[term_id]
    assert set(entry) <= {"term", "short", "source_url"}
    for text in (entry["term"], entry["short"]):
        assert re.search(r"[א-ת]", text), text
        assert not IDENTIFIER.search(text), f"מזהה קוד בתוך הסבר: {text!r}"
    if "source_url" in entry:
        assert entry["source_url"].startswith("https://")


def test_the_glossary_given_to_a_dossier_is_a_copy():
    given = glossary()
    given["deciding"]["short"] = "שונה"
    assert GLOSSARY["deciding"]["short"] != "שונה"


def test_every_certainty_level_is_explained_under_its_screen_label():
    for level, label in CERTAINTY_LABEL.items():
        entry = GLOSSARY.get(f"certainty_{level}")
        assert entry, f"רמת ודאות בלי הסבר: {level}"
        assert entry["term"] == label


def test_the_renamed_evidence_label_is_the_term_it_opens():
    """״תקרת הקטגוריה״ — השותפים שאלו תקרה של מה. התווית והמונח אומרים קומות."""
    assert FIELD_LABEL["category_ceiling"] == "מספר קומות מרבי לפי קטגוריית המדיניות"
    assert GLOSSARY[FIELD_TERM["category_ceiling"]]["term"] == FIELD_LABEL["category_ceiling"]
    for floors in set(rights.CATEGORY_CEILING.values()):
        assert f"{floors:g} קומות" in GLOSSARY["category_floors"]["short"]


def test_the_category_gate_speaks_of_floors_and_not_of_a_ceiling():
    r = rights.floors(12.5, "התחדשות מגרשית מוטת מגורים")
    detail = next(c.detail for c in r.checks if c.id == "renewal_policy_category")
    assert "עד 9 קומות" in detail and "תקרה" not in detail


def test_numbers_written_by_hand_in_the_glossary_match_the_code():
    a = get_assumptions("herzliya")
    assert f"ב-{get_settings().source_max_age_days} הימים" in GLOSSARY["deciding"]["short"]
    assert f"{MARGINAL_LAND_VALUE_ILS:,.0f} ₪" in GLOSSARY["levy_category"]["short"]
    assert f"({a.betterment_levy_rate.value:.0%})" in GLOSSARY["betterment_levy"]["short"]


# ── ״מכריע״ הוא אותו כלל שמכריע את השערים ──

def _field(days: float = 1, **override):
    f = {"value": 5, "certainty": "official", "location": "גוש 1 חלקה 1", "method": None,
         "source": {"url": "https://example.test/x",
                    "retrieved_at": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}}
    return {**f, **override}


def test_deciding_in_the_dossier_is_certainty_source_location_and_age_together():
    """הגרסה הקודמת בדקה ודאות בלבד, והמסך כתב שהעמודה משלבת ארבעה תנאים:
    ראיה רשמית שהתיישנה סומנה ״מכריע״, והשער שנשען עליה נשאר ״לא ידוע״."""
    stale = get_settings().source_max_age_days + 1
    rows = {r["field"]: r["decides"] for r in _evidence_rows({
        "fresh_official": _field(),
        "stale_official": _field(days=stale),
        "no_location": _field(location=None),
        "no_source": _field(source=None),
        "estimate": _field(certainty="estimate"),
        "empty": _field(value=None),
    })}
    assert rows == {"fresh_official": True, "stale_official": False, "no_location": False,
                    "no_source": False, "estimate": False, "empty": False}


def test_an_evidence_row_names_the_term_that_explains_it():
    rows = {r["field"]: r for r in _evidence_rows({"category_ceiling": _field(value=9.0),
                                                     "parcel_area": _field()})}
    assert rows["category_ceiling"]["term"] == "category_floors"
    assert rows["parcel_area"]["term"] is None


@pytest.mark.asyncio
async def test_a_delivered_dossier_carries_the_glossary(session):
    from tests.test_dossier import _delivered
    c, _, opp = await _delivered(session, block="9690")
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert _frontend_term_ids() <= set(d["glossary"])
    post_2005 = next(r for r in d["evidence"] if r["field"] == "post_2005_permit")
    assert post_2005["term"] == "post_2005" and post_2005["decides"] is True


# ── האקסל וה-PDF ──

def _dossier():
    from tests.test_exports import _with_economics
    return {**_with_economics(), "glossary": glossary()}


def test_the_excel_has_a_glossary_sheet_with_every_term():
    z = zipfile.ZipFile(io.BytesIO(exports.excel(_dossier())))
    assert 'name="מונחים"' in z.read("xl/workbook.xml").decode("utf-8")
    strings = z.read("xl/sharedStrings.xml").decode("utf-8")
    for entry in GLOSSARY.values():
        assert entry["term"] in strings and entry["short"] in strings, entry["term"]
    # גיליון התרחיש נשאר השני: ‏test_exports קורא אותו לפי המיקום
    assert "<f>" in z.read("xl/worksheets/sheet2.xml").decode("utf-8")


def test_the_pdf_ends_with_the_glossary_appendix():
    import pymupdf
    from app.cities.herzliya.surfaces import _words
    doc = pymupdf.open(stream=exports.pdf(_dossier()), filetype="pdf")
    lines = [_words(ln) for page in doc for ln in page.get_text().splitlines()]
    gaps = lines.index(frozenset({"פערים"}))
    appendix = lines.index(frozenset({"נספח", "מונחים"}))
    assert appendix > gaps, "הנספח צריך לבוא אחרי כל פרקי התיק"
    after = set().union(*lines[appendix:])
    assert {"מכריע", "ודאות", "רשמי"} <= after
