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
    # מספר עם סטטוס — בסיס ״חסר״ נכתב ריק תמיד (B13), ולכן הזיוף הוא של שומה
    claimed["economics"]["assumptions"]["betterment_base_ils"].update(value=4_000_000.0, status="data")
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


# ── B13 · הייצוא אומר מה הוא לא יודע ──

def _row(cells, label):
    import re as _re
    for ref, (kind, val) in cells.items():
        m = _re.fullmatch(r"A(\d+)", ref)
        if m and kind == "s" and val == label:
            n = m.group(1)
            return {col: cells.get(f"{col}{n}", ("blank", None)) for col in "BCDE"}
    raise AssertionError(f"לא נמצאה שורה: {label}")


@pytest.mark.asyncio
async def test_the_spreadsheet_says_where_each_input_came_from(session):
    """‏B8 מצא 22 קלטים באקסל בלי מקור: 45,000 היה מספר בלבד."""
    from app.cities.herzliya.surfaces import _cells
    d = await _dossier(session, "9666")
    cells = _cells(exports.excel(d))

    price = _row(cells, "מחיר מכירה למ״ר (כולל מע״מ)")
    assert price["B"] == ("n", 52_300.0)
    assert price["D"] == ("s", "נתון")                     # נפתר מעסקאות
    assert "17 עסקאות" in price["E"][1]

    unit = _row(cells, "שטח דירה קיימת ממוצע")
    assert unit["D"] == ("s", "אומדן")                     # לוח חלקי — מוצג, לא מכריע

    # ובסיס ההשבחה שאינו ידוע — תא ריק, וסטטוס שאומר את זה
    base = _row(cells, "ההשבחה (שומה)")
    assert base["B"][0] == "blank"
    assert base["D"] == ("s", "חסר")


@pytest.mark.asyncio
async def test_the_spreadsheet_carries_the_caveats_and_the_levy_ceiling(session):
    from app.cities.herzliya.surfaces import _cells
    d = await _dossier(session, "9667")
    econ = d["economics"]
    assert econ["caveats"] and econ["betterment"]["summary"]
    strings = {v for kind, v in _cells(exports.excel(d)).values() if kind == "s"}
    assert "על מה הרווח נשען" in strings
    assert econ["betterment"]["summary"] in strings
    for cav in econ["caveats"]:
        assert cav["text"] in strings, cav["id"]


@pytest.mark.asyncio
async def test_the_pdf_prints_the_ceiling_and_not_a_zero_levy(session):
    """״היטל השבחה: 0 ₪״ נקרא כמו ״אין היטל״. הבסיס דורש שומה."""
    import pymupdf
    from app.cities.herzliya.surfaces import _words
    d = await _dossier(session, "9668")
    doc = pymupdf.open(stream=exports.pdf(d), filetype="pdf")
    lines = [ln for page in doc for ln in page.get_text().splitlines()]

    levy_lines = [ln for ln in lines if {"היטל", "השבחה"} <= _words(ln)]
    assert levy_lines, "אין שורת היטל ב-PDF"
    assert not any(ln.replace("₪", "").strip().startswith("0 ") or " 0 " in f" {ln} " for ln in levy_lines), levy_lines
    assert any("ידוע" in _words(ln) and "נשמר" in _words(ln) for ln in levy_lines), levy_lines

    text = " ".join(lines)
    assert "נשען" in text                                   # כותרת הסייגים
    assert "רגל" in text                                    # ״טביעת רגל״ — השטח הקיים הוא אומדן
    # ומה שמכריע את B14 לא נשבר: המסך, ה-PDF והאקסל עדיין מסכימים
    assert compare(d, exports.excel(d), exports.pdf(d)) == []


def test_a_known_betterment_base_is_still_written_as_a_number():
    """הכלל ״ריק ולא 0״ חל רק כשהבסיס חסר. שומה אמיתית נכתבת כמספר."""
    from tests.test_exports import _with_economics
    d = _with_economics()
    row = d["economics"]["assumptions"]["betterment_base_ils"]
    row.update(value=12_000_000.0, status="data")
    assert exports._scenario_inputs(d)["levy_base"] == 12_000_000.0
    assert not exports._levy_unknown(d["economics"])
