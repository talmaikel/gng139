"""פרויקטים באותו רחוב — תקדים, ולא החלטה על קומות.

העירייה עצמה מבקשת את זה: המדריך לתכניות נקודתיות (2024) דורש ״ניתוח
מבנים גובלים: קווי בניין, גובה בינוי, האם קיימת זכאות מכח תמ"א 38״, והנוהל
(2025) מבקש להציג ״יוזמות התחדשות עירונית בסביבה, כולל תמ"א 38״.

**למה לא שכבת מספרי הבתים של העירייה.** ‏14.09.2026 נבדקו ביד שלושה
בניינים מול מדלן, והשכבה טעתה בשלושתם — כולל ״תמ"א 38/1, 7 קומות״ שהוא
בפועל פינוי-בינוי של שני מגדלים. מספר הקומות כאן נקרא **מהבקשה להיתר
עצמה**, ונשמר עם מספר הבקשה והכתובת שממנה נקרא.

**המסלול, והתקציב שלו** — לכל הזדמנות, לפי בקשה מפורשת, ולעולם לא לרחוב שלם
של העיר:

  1. שם הרחוב הקובע (החזית הצרה) נקרא מראיית `street_width`.
  2. קוד הרחוב מתוך קטלוג הרחובות העירוני — התאמה חד-ערכית או עצירה.
  3. ‏`GetBakashotByAddress` לרחוב, לפי סוג בקשה: ‏22 (היתר לתמ"א 38) ו-1
     (בקשה להיתר). עמוד אחד לכל סוג.
  4. מסננים מקומית, בלי רשת: חלון של ±`HOUSE_WINDOW` מספרי בית, בלי החלקה
     של הלקוח, ובקשות להיתר רגיל רק משנת `MIN_PERMIT_YEAR`.
  5. לכל היותר `MAX_REQUEST_PAGES` עמודי בקשה. לכל תיק — עד שנמצא פרויקט
     התחדשות שהופק לו היתר.

סה״כ לכל היותר 2 + `MAX_REQUEST_PAGES` פניות לארכיון (ועוד קטלוג הרחובות,
שנשמר במטמון). ‏CAPTCHA או עמוד ״לא ניתן להציג״ עוצרים את כל התהליך מיד
(`ArchiveBlocked`), ושום דבר חלקי אינו נכתב.

**פרטיות:** עמודת שם המבקש ברשימה, וטבלת ״בעלי עניין״ בעמוד הבקשה, **אינן
נקראות** — הפרסור ניגש לפי כותרת עמודה ולפי מקטע, לא מסנן אחר כך.

**ומה שאינו כאן:** הערך אינו מוזן ל-`rights.floors()` ואינו שער. הוא ראיה
שמוצגת ליזם, ומי שמכריע מספר קומות הוא הכלל ולא השכן.
"""
import argparse
import asyncio
import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, text

from app.cities.herzliya.archive_client import HerzliyaArchiveClient, HerzliyaArchiveError
from app.core.config import get_settings
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

FIELD = "neighbour_precedents"

# ‏22 = ״בקשה להיתר לתמ"א 38״, ‏1 = ״בקשה להיתר״ — מ-GetBakashotTypes, ‏14.09.2026.
# ‏45 (״רישוי מלא״) נבדק על הנוטרים והחזיר ריק; ראו השאלות הפתוחות.
LIST_TYPES = (22, 1)
TAMA38_PERMIT_TYPE = 22
HOUSE_WINDOW = 12
MIN_PERMIT_YEAR = 2006          # תמ"א 38 אושרה ב-2005; בקשות רגילות לפני כן אינן התחדשות
MAX_REQUEST_PAGES = 3

NOT_STATED = "לא צוין"

KIND_LABEL = {
    "tama38_1": 'תמ"א 38/1 · חיזוק ותוספת',
    "tama38_2": 'תמ"א 38/2 · הריסה ובנייה',
    "shaked": "חלופת שקד",
    "new_build": "הריסה ובנייה חדשה",
}

STATUS_LABEL = {
    "found": "נבדק",
    "none_found": "נבדק — לא נמצא פרויקט התחדשות עם היתר בחלון",
    "budget_reached": "נבדק חלקית — תקציב הפניות לארכיון נוצל",
    "no_street": "לא נבדק — שם הרחוב הקובע אינו ידוע",
    "street_not_matched": "לא נבדק — הרחוב הקובע לא זוהה בקטלוג העירוני",
    "no_anchor": "לא נבדק — מספר הבית של החלקה ברחוב הקובע אינו ידוע",
}


# ───────────────────────── טקסט ─────────────────────────

def _clean(fragment: str) -> str:
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html_lib.unescape(fragment.replace("&nbsp", " ")).replace("‏", " ").replace("‎", " ")
    return re.sub(r"\s+", " ", fragment).strip()


def _normalize_street(name: str) -> frozenset[str]:
    return frozenset(re.sub(r"[\"'״׳.\-־,()]", " ", name or "").split())


# תארים שמופיעים בקטלוג העירוני ולא בשם ה-OSM, או להפך: ״אלוף יגאל אלון״.
_TITLES = frozenset({"אלוף", "הרב", "רב", "דר", "ד", "ר", "שד", "שדרות", "רחוב", "פרופ", "פרופסור", "סמטת"})


# ───────────────────────── הרחוב הקובע ─────────────────────────

_FRONTAGE = re.compile(r"(\d+(?:\.\d+)?)\s*מ׳\s*[A-Za-z_]*\s*\(([^)]+)\)")
_DECISIVE = re.compile(r"הצרה קובעת\s*(\d+(?:\.\d+)?)")


def governing_street(location: str | None) -> str | None:
    """שם הרחוב שהחזית הצרה שלו קובעת, מתוך `location` של ראיית רוחב הרחוב.

    הפורמט הוא של `frontages.json` (שדה `why`): ״12.0 מ׳ residential (מוהליבר)
    · 37.9 מ׳ residential (הנוטרים) → הצרה קובעת 12.0״. חזית בלי שם, או שני
    שמות שונים באותו רוחב — אין רחוב קובע, ולא מנחשים.
    """
    decisive = _DECISIVE.search(location or "")
    if not decisive:
        return None
    width = float(decisive.group(1))
    names = {m.group(2).strip() for m in _FRONTAGE.finditer(location)
             if abs(float(m.group(1)) - width) < 0.05}
    return names.pop() if len(names) == 1 else None


def match_street(name: str | None, catalogue: list[dict[str, str]]) -> str | None:
    """קוד הרחוב בקטלוג העירוני. התאמה חד-ערכית בלבד."""
    wanted = _normalize_street(name or "")
    if not wanted:
        return None
    exact = {row["code"] for row in catalogue if _normalize_street(row["name"]) == wanted}
    if exact:
        return exact.pop() if len(exact) == 1 else None
    loose = set()
    for row in catalogue:
        tokens = _normalize_street(row["name"])
        if tokens and (tokens ^ wanted) <= _TITLES and (tokens >= wanted or wanted >= tokens):
            loose.add(row["code"])
    return loose.pop() if len(loose) == 1 else None


_HOUSE = re.compile(r"^(.*?)\s+(\d+)\s*[א-ת]?(?:\s+הרצליה)?\s*$")


def split_address(address: str | None) -> tuple[str | None, int | None]:
    """״הנוטרים 10 הרצליה״ → (״הנוטרים״, 10)."""
    m = _HOUSE.match((address or "").strip())
    return (m.group(1).strip(), int(m.group(2))) if m else (None, None)


# ───────────────────────── רשימת הבקשות ─────────────────────────

_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_DECLARED_REQUESTS = re.compile(r"נמצאו\s*(\d+)\s*בקשות")
_NO_RESULTS = ("לא אותרו תוצאות", "ERR_NO_RESULTS")

# העמודות שנקראות — לפי כותרת. ״שם המבקש״ אינה ברשימה, ולכן אינה נקראת.
_LIST_COLUMNS = {"מספר בקשה": "request", "תיק בניין": "tik", "כתובת": "address", "גוש": "gush", "חלקה": "helka"}


def parse_request_list(page: str) -> dict[str, Any]:
    """שורות מתוצאות `GetBakashotByAddress`. שם המבקש אינו נקרא."""
    head = page.find("<thead")
    if head < 0:
        if any(marker in page for marker in _NO_RESULTS):
            return {"status": "empty", "rows": [], "declared": 0, "complete": True}
        return {"status": "unrecognized", "rows": [], "declared": None, "complete": False}

    headers = [_clean(h) for h in _TH.findall(page[head:page.find("</thead>", head)])]
    index = {}
    for i, h in enumerate(headers):
        for label, key in _LIST_COLUMNS.items():
            if h.startswith(label) and key not in index:
                index[key] = i
    if "request" not in index or "address" not in index:
        return {"status": "unrecognized", "rows": [], "declared": None, "complete": False}

    rows = []
    body = page[page.find("<tbody", head):]
    for tr in _TABLE_ROW.findall(body):
        cells = _TD.findall(tr)
        if len(cells) <= max(index.values()):
            continue
        read = {key: _clean(cells[i]) for key, i in index.items()}   # רק העמודות שבמפה
        if not re.fullmatch(r"(19|20)\d{6}", read["request"]):
            continue
        street, house = split_address(read["address"])
        rows.append({
            "request": int(read["request"]),
            "tik": int(read["tik"]) if read.get("tik", "").isdigit() else None,
            "address": re.sub(r"\s*הרצליה\s*$", "", read["address"]),
            "street": street,
            "house_number": house,
            "gush": read.get("gush") or None,
            "helka": read.get("helka") or None,
        })
    declared = _DECLARED_REQUESTS.search(_clean(page))
    declared_n = int(declared.group(1)) if declared else len(rows)
    return {"status": "found" if rows else "empty", "rows": rows,
            "declared": declared_n, "complete": declared_n == len(rows)}


# ───────────────────────── עמוד הבקשה ─────────────────────────

_INFO_LABELS = {
    "מספר תיק בניין": "tik",
    "סוג הבקשה": "request_type",
    "שימוש עיקרי": "use",
    "תיאור הבקשה": "description",
    "מספר היתר": "permit",
    "תאריך הפקת היתר": "permit_date",
    "סך מספר יחידות דיור המבוקשות": "units_requested",
}


def _section(page: str, section_id: str) -> str:
    start = page.find(f'id="{section_id}"')
    if start < 0:
        return ""
    end = page.find('<div class="row" id="', start + 1)
    return page[start:end if end > 0 else len(page)]


def _iso(value: str | None) -> str | None:
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (value or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def parse_request_page(page: str) -> dict[str, Any]:
    """שני מקטעים בלבד: ״מידע כללי״ ו״מהות הבקשה״.

    ״בעלי עניין״ — מבקש, בעלים, עורך, מהנדס — הוא מקטע נפרד בעמוד, והוא
    **אינו נפתח**. שם שלא נקרא אינו יכול להישמר בטעות.
    """
    out: dict[str, Any] = {v: None for v in _INFO_LABELS.values()}
    for tr in _TABLE_ROW.findall(_section(page, "info-main")):
        cells = [_clean(c) for c in _TD.findall(tr)]
        if len(cells) >= 2 and cells[0] in _INFO_LABELS:
            out[_INFO_LABELS[cells[0]]] = cells[1] or None
    essence = [_clean(c) for c in _TD.findall(_section(page, "mahut"))]
    top = re.search(r"כתובת:\s*</div>\s*<div[^>]*>([^<]+)<", page)
    out["address"] = re.sub(r"\s*הרצליה\s*$", "", _clean(top.group(1))) if top else None
    out["essence"] = " ".join(e for e in essence if e) or None
    out["permit_date"] = _iso(out["permit_date"])
    units = out["units_requested"]
    out["units_requested"] = int(float(units)) if units and re.fullmatch(r"\d+(?:\.0+)?", units) else None
    return out


# ───────────────────────── סיווג ─────────────────────────

_TAMA38 = re.compile(r'תמ["״\']?\s*א\s*38|תמא\s*38')
_SHAKED = re.compile(r"חלופת\s*שקד|תיקון\s*139|סעיף\s*70\s*א")
# הריסה **של בניין**. ״הריסת מדרגות קיימות״ מופיע בכל תוספת מעלית.
_DEMOLISH = re.compile(r"הריס(?:ה|ת)\s+(?:ה)?(?:בני[י]?ן|מבנה|בית|המבנים|מבנים)|הריסה\s+ובני[י]?ה")
_NEW = re.compile(r"(?:בני[י]?ן|מבנה|בית(?:\s+מגורים)?)\s+(?:\S+\s+){0,2}חדש|הקמת\s+(?:ה)?(?:בני[י]?ן|מבנה|בית)")


def classify(request: dict[str, Any]) -> str | None:
    """סוג ההתחדשות, או None — רק ממילים מפורשות בבקשה עצמה."""
    blob = " ".join(filter(None, (request.get("request_type"), request.get("description"), request.get("essence"))))
    if _SHAKED.search(blob):
        return "shaked"
    if _TAMA38.search(blob):
        return "tama38_2" if _DEMOLISH.search(blob) else "tama38_1"
    if _DEMOLISH.search(blob) and _NEW.search(blob):
        return "new_build"
    return None


# ───────────────────────── קומות ויחידות ─────────────────────────
#
# **רק סכום מפורש של הבניין שנבנה.** המהות של בקשת תמ"א 38 מתארת שלושה
# מספרים שונים בשורות סמוכות — מהבקשה 20130622, כלשונה:
#
#   ״בית מגורים משותף בן 3 קומות על עמודים,12 יחי"ד״      ← הקיים
#   ״תוספת 2.5 קומות, 6 יחי"דיור״                          ← התוספת
#   ״סה"כ 6.5 קומות כולל קומת הקרקע, סה"כ 18 יחי"דיור״     ← הבניין שיהיה
#
# רק השלישי נקרא. גם ״סך מספר יחידות דיור המבוקשות״ (6 שם) הוא התוספת, ולכן
# הוא נשמר בנפרד ואינו ״יחידות״.

_NUM = r"(\d+(?:\.\d+)?)"
_TOTAL = r'סה["״]?\s*כ\s*:?\s*'
_UNITS_WORD = r'(?:יח(?:י)?["״\']?\s*ד(?:יור)?|יחידות\s*דיור|דירות)'

_FLOORS_EXPLICIT = (
    re.compile(_TOTAL + _NUM + r"\s*קומות"),
    re.compile(_NUM + r"\s*קומות\s*כולל\s*(?:את\s*)?(?:ק(?:ומת)?\s*[.׳']?\s*(?:ה)?קרקע)"),
)
# בבניין חדש כל הבניין הוא ״הבניין שיהיה״, ולכן גם ״בניין חדש בן 8 קומות״.
_FLOORS_NEW_BUILDING = re.compile(r"חדש\S*\s+בן\s+" + _NUM + r"\s*קומות")
_UNITS_EXPLICIT = re.compile(_TOTAL + r"(\d+)\s*" + _UNITS_WORD)
_UNITS_ANY = re.compile(r"(\d+)\s*" + _UNITS_WORD)
_WHOLE_BUILDING_KINDS = frozenset({"tama38_2", "new_build", "shaked"})


def _accepted(text_: str, patterns, *, reject_prefix=r"קיימ|תוספת|בן\s*$") -> tuple[set[float], str | None]:
    values, quote = set(), None
    for pattern in patterns:
        for m in pattern.finditer(text_):
            if re.search(reject_prefix, text_[max(0, m.start() - 25):m.start()]):
                continue
            values.add(float(m.group(1)))
            quote = quote or m.group(0).strip()
    return values, quote


def parse_floors(text_: str | None, kind: str | None) -> dict[str, Any]:
    """מספר הקומות של הבניין שנבנה, כלשון הבקשה. אחד חד-משמעי, או ״לא צוין״."""
    text_ = text_ or ""
    patterns = list(_FLOORS_EXPLICIT) + ([_FLOORS_NEW_BUILDING] if kind in _WHOLE_BUILDING_KINDS else [])
    values, quote = _accepted(text_, patterns)
    if len(values) == 1:
        return {"value": values.pop(), "quote": quote}
    return {"value": None, "quote": None,
            "note": "מספרים סותרים בתיאור" if len(values) > 1 else NOT_STATED}


def parse_units(text_: str | None, kind: str | None) -> dict[str, Any]:
    text_ = text_ or ""
    values, quote = _accepted(text_, [_UNITS_EXPLICIT])
    if not values and kind in _WHOLE_BUILDING_KINDS:
        values, quote = _accepted(text_, [_UNITS_ANY])
    if len(values) == 1:
        return {"value": int(values.pop()), "quote": quote}
    return {"value": None, "quote": None,
            "note": "מספרים סותרים בתיאור" if len(values) > 1 else NOT_STATED}


# ───────────────────────── איסוף ─────────────────────────

def _year(request_no: int) -> int:
    return int(str(request_no)[:4])


def _candidates(rows_by_type: dict[int, list[dict]], anchor: int, own: tuple[str, str] | None,
                window: int) -> list[list[dict]]:
    """קבוצות לפי תיק, בסדר שבו כדאי להוציא עליהן את התקציב."""
    seen: dict[int, dict] = {}
    for t in LIST_TYPES:                                       # 22 קודם: אותה בקשה נשמרת עם הסוג המפורש
        for r in rows_by_type.get(t, []):
            if r["request"] in seen or r["house_number"] is None:
                continue
            if abs(r["house_number"] - anchor) > window:
                continue
            if own and (r["gush"], r["helka"]) == own:
                continue
            if t != TAMA38_PERMIT_TYPE and _year(r["request"]) < MIN_PERMIT_YEAR:
                continue
            seen[r["request"]] = {**r, "list_type": t, "house_number_gap": abs(r["house_number"] - anchor)}

    groups: dict[Any, list[dict]] = {}
    for r in seen.values():
        groups.setdefault(r["tik"] or r["address"], []).append(r)
    for g in groups.values():
        # היתר תמ"א 38 המקורי קודם לתכניות השינויים שאחריו; בבקשה רגילה —
        # החדשה ביותר היא זו שסביר שהיא הבנייה מחדש.
        g.sort(key=lambda r: (r["list_type"] != TAMA38_PERMIT_TYPE,
                              r["request"] if r["list_type"] == TAMA38_PERMIT_TYPE else -r["request"]))
    return sorted(groups.values(), key=lambda g: (
        all(r["list_type"] != TAMA38_PERMIT_TYPE for r in g),
        min(r["house_number_gap"] for r in g),
        -max(r["request"] for r in g)))


async def collect(client: HerzliyaArchiveClient, street_code: str, *, anchor: int | None,
                  own_parcel: tuple[str, str] | None, window: int = HOUSE_WINDOW,
                  max_pages: int = MAX_REQUEST_PAGES) -> dict[str, Any]:
    """הפניות לארכיון, והפרסור. אינו נוגע במסד. ‏`ArchiveBlocked` עובר הלאה."""
    lists, rows_by_type = [], {}
    for t in LIST_TYPES:
        page, meta = await client.requests_by_address(street_code, t)
        parsed = parse_request_list(page)
        if parsed["status"] == "unrecognized":
            raise HerzliyaArchiveError(f"Unrecognised request-list page for street {street_code}, type {t}")
        rows_by_type[t] = parsed["rows"]
        lists.append({"request_type": t, "source_url": meta.get("url"), "retrieved_at": meta.get("retrieved_at"),
                      "rows": len(parsed["rows"]), "declared": parsed["declared"], "complete": parsed["complete"]})

    if anchor is None and own_parcel:
        # החלקה עצמה ברשימה נותנת את מספר הבית שלה ברחוב הקובע.
        own_rows = {r["house_number"] for rows in rows_by_type.values() for r in rows
                    if (r["gush"], r["helka"]) == own_parcel and r["house_number"] is not None}
        anchor = own_rows.pop() if len(own_rows) == 1 else None
    base = {"lists": lists, "anchor_house_number": anchor, "window": window, "max_request_pages": max_pages}
    if anchor is None:
        return {**base, "status": "no_anchor", "projects": [], "requests_checked": []}

    groups = _candidates(rows_by_type, anchor, own_parcel, window)
    projects, checked, pages, exhausted = [], [], 0, False
    for group in groups:
        for r in group:
            if pages >= max_pages:
                exhausted = True
                break
            page, meta = await client.request_page(r["request"])
            pages += 1
            req = parse_request_page(page)
            kind = classify(req)
            checked.append({"request": r["request"], "kind": kind, "has_permit": bool(req["permit_date"])})
            if not (kind and req["permit_date"]):
                continue
            blob = " ".join(filter(None, (req["description"], req["essence"])))
            floors, units = parse_floors(blob, kind), parse_units(blob, kind)
            projects.append({
                "address": req["address"] or r["address"],
                "house_number": r["house_number"],
                "house_number_gap": r["house_number_gap"],
                "gush": r["gush"], "helka": r["helka"], "tik": r["tik"],
                "request": r["request"],
                "request_type": req["request_type"],
                "kind": kind, "kind_label": KIND_LABEL[kind],
                "floors": floors["value"], "floors_quote": floors["quote"],
                "units": units["value"], "units_quote": units["quote"],
                "units_requested": req["units_requested"],
                "permit_year": int(req["permit_date"][:4]),
                "distance_m": None,
                "source_url": meta.get("url"),
                "retrieved_at": meta.get("retrieved_at"),
            })
            break                                           # פרויקט אחד לתיק
        if exhausted:
            break

    status = "budget_reached" if exhausted else ("found" if projects else "none_found")
    return {**base, "status": status, "projects": projects, "requests_checked": checked}


# ───────────────────────── מסד ─────────────────────────

def _street_location(fields: dict[str, dict]) -> str | None:
    street = fields.get("street_width") or {}
    for obs in street.get("observations") or [street]:
        if obs.get("location") and _DECISIVE.search(obs["location"]):
            return obs["location"]
    return None


def _fresh(field: dict | None, now: datetime) -> bool:
    """שליפה שנעשתה — ולא ״לא נבדק״, שאין בו מה לשמור במטמון."""
    retrieved = ((field or {}).get("source") or {}).get("retrieved_at")
    if not retrieved or (field or {}).get("certainty") != Certainty.DERIVED.value:
        return False
    return now - datetime.fromisoformat(retrieved) < timedelta(days=get_settings().source_max_age_days)


async def _distances(session, opp: Opportunity, projects: list[dict]) -> None:
    """מרחק במטרים — רק לחלקות שכבר במסד. אין פנייה לרשת בשביל זה."""
    for p in projects:
        if not (p["gush"] and p["helka"]):
            continue
        row = (await session.execute(text(
            "SELECT ST_Distance(o.geom::geography, c.geom::geography) FROM opportunities o, opportunities c "
            "WHERE c.id = :cid AND o.city_code = c.city_code AND o.block = :g AND o.parcel = :h LIMIT 1"),
            {"cid": opp.id, "g": p["gush"], "h": p["helka"]})).scalar_one_or_none()
        p["distance_m"] = round(row) if row is not None else None


async def fetch_for_dossier(session, opportunity_id: UUID, client: HerzliyaArchiveClient | None = None,
                            *, now: datetime | None = None) -> dict[str, Any]:
    """שליפת תקדימי הרחוב להזדמנות אחת, וכתיבתם כראיה. ‏flush ולא commit."""
    from app.services.evidence_store import fields_for

    now = now or datetime.now(timezone.utc)
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise LookupError("ההזדמנות אינה קיימת")
    fields = await fields_for(session, opportunity_id)
    if _fresh(fields.get(FIELD), now):
        return {**fields[FIELD]["value"], "from_cache": True}

    name = governing_street(_street_location(fields))
    if not name:
        return await _write(session, opp.id, {"status": "no_street", "projects": []}, None, now)

    own = client is None
    client = client or HerzliyaArchiveClient()
    try:
        catalogue = (await client.streets())["streets"]
        code = match_street(name, catalogue)
        street = {"name": name, "code": code}
        if not code:
            return await _write(session, opp.id, {"status": "street_not_matched", "street": street, "projects": []},
                                None, now)
        addr_street, addr_house = split_address(opp.address)
        anchor = addr_house if addr_street and match_street(addr_street, catalogue) == code else None
        value = await collect(client, code, anchor=anchor,
                              own_parcel=(opp.block, opp.parcel) if opp.block and opp.parcel else None)
    finally:
        if own:
            await client.close()

    value["street"] = street
    await _distances(session, opp, value["projects"])
    # מועד השליפה המקורי מהמטמון, ולא רגע הכתיבה: עמוד שנשלף לפני שבוע נושא את התאריך שלו.
    stamps = [x["retrieved_at"] for x in value["lists"] + value["projects"] if x.get("retrieved_at")]
    when = datetime.fromisoformat(min(stamps)) if stamps else now
    return await _write(session, opp.id, value, value["lists"][0]["source_url"], when)


async def _write(session, oid: UUID, value: dict, source_url: str | None, now: datetime) -> dict:
    value = {**value, "status_label": STATUS_LABEL[value["status"]]}
    checked = len(value.get("requests_checked") or [])
    await session.execute(delete(FieldEvidence).where(FieldEvidence.opportunity_id == oid,
                                                      FieldEvidence.field == FIELD))
    session.add(FieldEvidence(
        opportunity_id=oid, field=FIELD, value=value,
        certainty=(Certainty.DERIVED if source_url else Certainty.MISSING).value,
        source_url=source_url, retrieved_at=now,
        location=f'רחוב {(value.get("street") or {}).get("name") or "—"} · '
                 f'{len(value["projects"])} פרויקטים · {checked} עמודי בקשה',
        method=(f"GetBakashotByAddress סוגים {','.join(map(str, LIST_TYPES))} · חלון ±{HOUSE_WINDOW} מספרי בית · "
                f"עד {MAX_REQUEST_PAGES} עמודי בקשה · קומות רק מסכום מפורש בבקשה · שם המבקש אינו נקרא")))
    await session.flush()
    return value


async def _main(argv=None):
    """הזדמנות אחת, לפי מזהה. אין כאן ״כל הרחוב״ ואין ״כל העיר״."""
    from app.core.database import AsyncSessionLocal
    ap = argparse.ArgumentParser(description="פרויקטים באותו רחוב, להזדמנות אחת")
    ap.add_argument("id", help="מזהה הזדמנות")
    a = ap.parse_args(argv)
    async with AsyncSessionLocal() as session:
        out = await fetch_for_dossier(session, UUID(a.id))
        await session.commit()
    return out


if __name__ == "__main__":
    print(asyncio.run(_main()))
