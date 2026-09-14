"""‏B14 · מסך = PDF = אקסל, על תיק שנבנה מקצה לקצה.

שני סוגי בדיקות כאן, ושניהם נחוצים:

- **התיק אמיתי ומסכים** — ‏`build()` על חלקה נמסרת, הקבצים מופקים
  ונקראים חזרה, ואין סתירה.
- **הבדיקה תופסת** — מזייפים משטח אחד בכוונה, ומוודאים שהסתירה מדווחת.
  בלי זה, ״אין סתירות״ יכול להיות גם בודק שלא קרא כלום.
"""
import copy

import pytest

from app.cities.herzliya import exports
from app.cities.herzliya.dossier import build
from app.cities.herzliya.rules import HerzliyaCityRules
from app.cities.herzliya.surfaces import compare, excel_surface, pdf_surface
from tests.test_dossier import _delivered, _with_resolved_inputs


async def _dossier(session, block, resolved=True):
    if resolved:
        c, opp = await _with_resolved_inputs(session, block)
    else:
        c, _, opp = await _delivered(session, block=block)
    d = await build(session, HerzliyaCityRules(), opp.id, c.id)
    assert d["economics"]["scenario"] is not None, "הבדיקה צריכה תרחיש מחושב"
    return d


# ── התיק האמיתי ──

@pytest.mark.asyncio
async def test_a_delivered_dossier_shows_one_number_on_every_surface(session):
    """מחיר מעסקאות ושטח דירה מלוח — שני הקלטים שבהם האקסל סטה ביום שני."""
    d = await _dossier(session, "9660")
    xlsx, pdf = exports.excel(d), exports.pdf(d)
    assert compare(d, xlsx, pdf) == []

    # ולא בגלל שלא נקרא כלום
    sheet, doc = excel_surface(xlsx), pdf_surface(pdf)
    s = d["economics"]["scenario"]
    assert sheet.profit == pytest.approx(s["projected_profit_ils"], abs=1)
    assert doc.profit == pytest.approx(s["projected_profit_ils"], abs=1)
    assert sheet.total_cost == pytest.approx(s["total_cost_ils"], abs=1)
    assert doc.total_cost == pytest.approx(s["total_cost_ils"], abs=2)
    assert sheet.levy_base is not None


@pytest.mark.asyncio
async def test_a_dossier_on_city_defaults_agrees_as_well(session):
    d = await _dossier(session, "9661", resolved=False)
    assert compare(d, exports.excel(d), exports.pdf(d)) == []


# ── הבדיקה תופסת ──

@pytest.mark.asyncio
async def test_the_monday_bug_is_caught(session):
    """הבאג של יום שני, משוחזר: האקסל נכתב ממחיר העיר, והמסך מהמחיר לחלקה."""
    d = await _dossier(session, "9662")
    stale = copy.deepcopy(d)
    stale["economics"]["assumptions"]["sale_price_per_sqm_ils"]["value"] = 45_000.0

    problems = compare(d, exports.excel(stale), exports.pdf(d))
    assert any(p.startswith("רווח:") and "אקסל" in p for p in problems), problems


@pytest.mark.asyncio
async def test_a_pdf_that_prints_a_different_profit_is_caught(session):
    d = await _dossier(session, "9663")
    other = copy.deepcopy(d)
    other["economics"]["scenario"]["projected_profit_ils"] += 250_000

    problems = compare(d, exports.excel(d), exports.pdf(other))
    assert any(p.startswith("רווח:") and "PDF" in p for p in problems), problems
    # רווח שונה עם אותן הכנסות הוא גם עלות שונה
    assert any(p.startswith("סך העלויות:") and "PDF" in p for p in problems), problems


@pytest.mark.asyncio
async def test_a_betterment_base_that_differs_is_caught_and_a_blank_one_is_not(session):
    """‏B13 הופך את התא לריק. ריק אינו סתירה — אקסל מחשב אותו כ-0, כמו
    השרת. מספר אחר כן סתירה."""
    d = await _dossier(session, "9664")
    assert not d["economics"]["assumptions"]["betterment_base_ils"]["value"]

    claimed = copy.deepcopy(d)
    claimed["economics"]["assumptions"]["betterment_base_ils"]["value"] = 4_000_000.0
    problems = compare(d, exports.excel(claimed), exports.pdf(d))
    assert any(p.startswith("בסיס ההשבחה:") for p in problems), problems

    blank = copy.deepcopy(d)
    blank["economics"]["assumptions"]["betterment_base_ils"]["value"] = None
    assert excel_surface(exports.excel(blank)).levy_base == 0.0
    assert compare(d, exports.excel(blank), exports.pdf(d)) == []


@pytest.mark.asyncio
async def test_a_loss_keeps_its_minus_sign_in_the_pdf(session):
    """בסדר תצוגה המינוס יכול לעבור לצד השני של המספר. הפסד שנקרא
    כרווח הוא הטעות הכי יקרה שהבדיקה הזו יכולה לעשות בעצמה."""
    d = await _dossier(session, "9665")
    loss = copy.deepcopy(d)
    s = loss["economics"]["scenario"]
    s["projected_profit_ils"] = -3_142_113.0
    s["profit_margin_on_cost_ratio"] = -0.21

    doc = pdf_surface(exports.pdf(loss))
    assert doc.profit == -3_142_113.0
    assert doc.margin == "-21%"
