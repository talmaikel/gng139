"""‏B14 · אותו תיק, שלושה משטחים — ומספר אחד.

היזם רואה את התרחיש בשלושה מקומות: במסך (ה-JSON שהשרת מחזיר), ב-PDF
ובאקסל. ביום שני התברר שהם לא מראים את אותו מספר: ‏6537/120 הראתה
‏14.7% במסך ו-28.8% באקסל. **וה-CI היה ירוק**, כי הבדיקה שהשוותה אקסל
לחישוב רצה על ערכי הספרייה — בדיוק המקרה שבו אין הבדל.

המודול הזה **קורא את הקבצים עצמם**, ולא את הקוד שכתב אותם:

- **אקסל:** פותח את ה-xlsx, לוקח מכל תא את הערך או את הנוסחה כפי שנשמרו,
  ומחשב את הנוסחאות לפי הפניות התאים שבקובץ. שורה שזזה בקוד בלי שהנוסחה
  זזה איתה — נתפסת כאן.
- **PDF:** מחלץ את הטקסט המצויר. ‏reportlab מצייר עברית בסדר תצוגה, ולכן
  הטקסט שיוצא הפוך בסדר המילים ובסוגריים; שורה מזוהה לפי **אוסף המילים**
  שבה, שאינו תלוי בסדר.

מה מושווה, ולמה דווקא זה:

- **רווח ועלות** — בשלושת המשטחים. ה-PDF אינו מדפיס ״סך העלויות״, אבל
  מדפיס הכנסות ורווח, והעלות היא ההפרש ביניהם.
- **בסיס ההשבחה** — באקסל מול השרת. תא ריק נחשב 0, כמו שאקסל עצמו מחשב
  אותו; כך B13 (״ריק ולא 0״) לא מפיל את הבדיקה, ומספר אחר כן.
- **שורת ההיטל ב-PDF אינה מושווית.** ‏B13 מחליף אותה בתקרה, וזה שינוי
  ניסוח ולא סתירה.

המודול אינו תלוי במסד ואינו פונה לרשת: הוא מקבל תיק מוכן ומחזיר רשימת
סתירות. ‏`tests/test_surfaces.py` מריץ אותו על תיק מפיקסטורה, ו-
‏`scripts/check_surfaces.py` על החלקות שנזרעו ב-CI.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

MONEY_TOLERANCE_ILS = 1.0     # ה-PDF מעגל לשקל
SCENARIO_SHEET = "תרחיש"
OUTPUT_HEADER = "חישוב"       # הכותרת שמעל שורות הנוסחאות באקסל

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


@dataclass
class Surface:
    """מה שמשטח אחד מראה. ‏`None` — המשטח אינו מציג את המספר."""
    name: str
    revenue: float | None = None
    total_cost: float | None = None
    profit: float | None = None
    margin: float | str | None = None   # ב-PDF: המחרוזת שהודפסה
    levy_base: float | None = None
    problems: list[str] = field(default_factory=list)


# ── השרת ──

def server_surface(d: dict[str, Any]) -> Surface:
    econ = d["economics"]
    s = econ.get("scenario") or {}
    base = (econ.get("assumptions") or {}).get("betterment_base_ils") or {}
    return Surface("מסך", revenue=s.get("total_revenue_ils"),
                   total_cost=s.get("total_cost_ils"),
                   profit=s.get("projected_profit_ils"),
                   margin=s.get("profit_margin_on_cost_ratio"),
                   levy_base=base.get("value"))


# ── אקסל ──

class _ExcelError(Exception):
    """מה שאקסל היה מציג כ-#VALUE! או #DIV/0!."""


def _sheet_xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels.findall("rel:Relationship", _NS)}
    for sh in wb.find("m:sheets", _NS):
        if sh.get("name") == name:
            path = target[sh.get(f"{{{_NS['r']}}}id")].lstrip("/")
            return ET.fromstring(z.read(path if path.startswith("xl/") else f"xl/{path}"))
    raise KeyError(f"אין גיליון בשם {name}")


def _cells(xlsx: bytes) -> dict[str, tuple[str, Any]]:
    """כל תא בגיליון התרחיש: ‏('n', מספר) · ('s', טקסט) · ('f', נוסחה) · ('blank', None)."""
    z = zipfile.ZipFile(io.BytesIO(xlsx))
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            strings.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    out: dict[str, tuple[str, Any]] = {}
    for c in _sheet_xml(z, SCENARIO_SHEET).iter(f"{{{_NS['m']}}}c"):
        ref, f, v = c.get("r"), c.find("m:f", _NS), c.find("m:v", _NS)
        if f is not None and f.text:
            out[ref] = ("f", f.text)
        elif c.get("t") == "s" and v is not None:
            out[ref] = ("s", strings[int(v.text)])
        elif c.get("t") == "inlineStr":
            out[ref] = ("s", "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t")))
        elif v is not None and v.text is not None:
            out[ref] = ("n", float(v.text))
        else:
            out[ref] = ("blank", None)
    return out


_REF = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")


def _evaluate(cells: dict[str, tuple[str, Any]], ref: str, seen: frozenset = frozenset()) -> Any:
    """מחשב תא כמו שאקסל מחשב אותו — רק מה שהגיליון שלנו משתמש בו:
    ארבע פעולות, השוואה, ‏MIN, ‏MAX, ‏ROUND ו-IF. **תא ריק בחשבון הוא 0**, כמו באקסל."""
    if ref in seen:
        raise _ExcelError(f"הפניה מעגלית ב-{ref}")
    kind, val = cells.get(ref, ("blank", None))
    if kind == "blank":
        return None
    if kind != "f":
        return val

    def arg(r: str) -> Any:
        v = _evaluate(cells, r, seen | {ref})
        return 0.0 if v is None else v

    expr = _REF.sub(lambda m: f'arg("{m.group(1)}{m.group(2)}")', val)
    expr = (expr.replace("<>", "!=").replace("MIN(", "_min(").replace("MAX(", "_max(")
            .replace("ROUND(", "_round(").replace("IF(", "_if("))
    expr = re.sub(r"(?<![<>!=])=(?!=)", "==", expr)

    def _min(*xs):
        nums = [x for x in xs if isinstance(x, (int, float))]
        return min(nums) if nums else 0.0

    def _max(*xs):
        nums = [x for x in xs if isinstance(x, (int, float))]
        return max(nums) if nums else 0.0

    def _round(x, n=0):
        # ‏ROUND באקסל מעגל חצי הרחק מאפס; המחשבון מעגל חצי כלפי מעלה על חיוביים.
        return float(int(x * 10 ** n + 0.5)) / 10 ** n

    def _if(cond, a, b):
        return a if cond else b

    try:
        return eval(expr, {"__builtins__": {}},
                    {"arg": arg, "_min": _min, "_max": _max, "_round": _round, "_if": _if})
    except ZeroDivisionError as e:
        raise _ExcelError(f"#DIV/0! ב-{ref}") from e
    except TypeError as e:
        raise _ExcelError(f"#VALUE! ב-{ref}: {e}") from e


def excel_surface(xlsx: bytes) -> Surface:
    """השורות מזוהות לפי התווית בעמודה A — ‏*אחרי* כותרת ״חישוב״, כי
    ״מימון״ ו״שיווק ותיווך״ מופיעים גם בקלטים וגם בחישוב."""
    out = Surface("אקסל")
    cells = _cells(xlsx)
    rows = sorted({int(_REF.fullmatch(r).group(2)) for r in cells if _REF.fullmatch(r)})
    section = "inputs"
    wanted_out = {"הכנסות היזם (נטו ממע״מ)": "revenue", "סך העלויות": "total_cost",
                  "רווח": "profit", "רווח על העלות": "margin"}
    for n in rows:
        kind, label = cells.get(f"A{n}", ("blank", None))
        if kind != "s":
            continue
        if label == OUTPUT_HEADER:
            section = "outputs"
            continue
        if section == "inputs" and label.startswith("ההשבחה"):
            v = cells.get(f"B{n}", ("blank", None))
            out.levy_base = 0.0 if v[0] == "blank" else v[1]
        elif section == "outputs" and label in wanted_out:
            try:
                v = _evaluate(cells, f"B{n}")
            except _ExcelError as e:
                out.problems.append(f"האקסל מציג שגיאה בשורה ״{label}״: {e}")
                continue
            setattr(out, wanted_out[label], None if v == "" else v)
    for attr, lbl in (("revenue", "הכנסות"), ("profit", "רווח"), ("total_cost", "סך העלויות")):
        if getattr(out, attr) is None and not any(lbl in p for p in out.problems):
            out.problems.append(f"לא נמצאה באקסל שורת ״{lbl}״")
    return out


# ── PDF ──

_WORD = re.compile(r"[א-ת״׳\"']+")
# ‏**הסימן יכול לעבור לצד השני של המספר.** בסדר תצוגה, ‏`-3,000,000 ₪`
# עלול להיות מצויר ‏`₪ 3,000,000-`. מינוס משני הצדדים נחשב.
_SHEKEL = re.compile(r"₪\s*(-?)(\d{1,3}(?:,\d{3})*)(-?)|(-?)(\d{1,3}(?:,\d{3})*)(-?)\s*₪")
# באחוז המינוס מצויר *אחרי* סימן האחוז: ‏`-21%` יוצא ‏`21%-`. נמצא בבדיקה.
_PERCENT = re.compile(r"(-?)(\d+)\s*%(-?)|%\s*(-?)(\d+)(-?)")


def _signed(m: re.Match) -> str:
    g = m.groups()
    sign, digits, tail = (g[0], g[1], g[2]) if g[1] is not None else (g[3], g[4], g[5])
    return ("-" if "-" in (sign or "") + (tail or "") else "") + digits


def _words(text: str) -> frozenset[str]:
    return frozenset(w.strip("\"'") for w in _WORD.findall(text) if w.strip("\"'"))


def pdf_surface(pdf: bytes) -> Surface:
    import pymupdf

    out = Surface("PDF")
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    lines = [ln for page in doc for ln in page.get_text().splitlines()]
    for ln in lines:
        if "₪" not in ln:
            continue
        words, money = _words(ln), _SHEKEL.search(ln)
        if not money:
            continue
        amount = float(_signed(money).replace(",", ""))
        if words == _words("הכנסות היזם (נטו ממע״מ)") and out.revenue is None:
            out.revenue = amount
        elif words == _words("רווח על העלות") and out.profit is None:
            out.profit = amount
            # האחוז נשמר כמחרוזת: ההשוואה נעשית באותו עיגול שה-PDF הדפיס
            pct = _PERCENT.search(_SHEKEL.sub(" ", ln))
            out.margin = f"{_signed(pct)}%" if pct else None
    if out.revenue is None:
        out.problems.append("לא נמצאה ב-PDF שורת ״הכנסות״")
    if out.profit is None:
        out.problems.append("לא נמצאה ב-PDF שורת ״רווח״")
    if out.revenue is not None and out.profit is not None:
        out.total_cost = out.revenue - out.profit
    return out


# ── ההשוואה ──

def compare(d: dict[str, Any], xlsx: bytes, pdf: bytes) -> list[str]:
    """רשימת סתירות בעברית, ריקה כשהשלושה מסכימים. תיק בלי תרחיש אינו
    נבדק — אין בו מספרים להשוות, וזה נאמר ולא נבלע."""
    server = server_surface(d)
    if server.profit is None:
        return []
    problems: list[str] = []
    excel, pdf_ = excel_surface(xlsx), pdf_surface(pdf)
    problems += excel.problems + pdf_.problems

    def money(label: str, attr: str, *others: Surface) -> None:
        want = getattr(server, attr)
        for o in others:
            got = getattr(o, attr)
            if got is None or want is None:
                continue
            # ה-PDF מעגל כל שורה לשקל, והעלות בו היא הפרש של שתי שורות מעוגלות
            tol = MONEY_TOLERANCE_ILS * (2 if o.name == "PDF" and attr == "total_cost" else 1)
            if abs(got - want) > tol:
                problems.append(f"{label}: {server.name} {want:,.0f} ₪, {o.name} {got:,.0f} ₪")

    money("רווח", "profit", excel, pdf_)
    money("סך העלויות", "total_cost", excel, pdf_)
    money("הכנסות", "revenue", excel, pdf_)

    if server.margin is not None:
        if excel.margin is not None and abs(excel.margin - server.margin) > 5e-5:
            problems.append(f"רווח על העלות: {server.name} {server.margin:.2%}, "
                            f"אקסל {excel.margin:.2%}")
        # ה-PDF מדפיס אחוז שלם; משווים לאותה מחרוזת בדיוק, לא לעיגול שלנו
        if pdf_.margin is not None and f"{server.margin:.0%}" != pdf_.margin:
            problems.append(f"רווח על העלות: {server.name} {server.margin:.0%}, "
                            f"PDF {pdf_.margin}")
        elif pdf_.margin is None and not pdf_.problems:
            problems.append("לא נמצא ב-PDF האחוז של הרווח על העלות")

    want_base = server.levy_base or 0.0
    if excel.levy_base is not None and abs(excel.levy_base - want_base) > MONEY_TOLERANCE_ILS:
        problems.append(f"בסיס ההשבחה: {server.name} {want_base:,.0f} ₪, "
                        f"אקסל {excel.levy_base:,.0f} ₪")
    elif excel.levy_base is None:
        problems.append("לא נמצא באקסל תא בסיס ההשבחה")
    return problems
