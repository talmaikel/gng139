"""שני השערים שרק הארכיון יכול לענות עליהם, ורק לרשימה קצרה.

‏§70א(2) שואל אם המבנה **חוזק בהיתר** — ואם כן הוא פסול. ושאלה מסחרית
נפרדת היא אם **יזם אחר כבר בתמונה**: בקשת חיזוק שהוגשה ולא הבשילה להיתר.
שתיהן קיימות רק בתיק הבניין, ולכן לא ניתן להעריך אותן משום מקור אחר.

**המודול הזה אינו סורק.** הוא מקבל רשימת הזדמנויות ומביא תיק לכל אחת,
כי הארכיון עונה לפרצי בקשות ב-429 ובחלק מהמקרים ב-CAPTCHA. התבנית שנקבעה
בארכיטקטורה היא זולה על 700 ויקרה על עשר — והמגבלה כאן אוכפת אותה.

**פרטיות:** עמודת שם המבקש היא `i+3` בשורת הבקשה, והיא מדולגת **בזמן
הפרסור** ולא מסוננת אחר כך. שם שלא נקרא אינו יכול להישמר בטעות.

‏**W5 · 16.09 · מה העמוד באמת מציג.** סדר העמודות בתיק: מספר בקשה · תאריך
הגשה · **ארוע אחרון להצגה** · שם המבקש · היתר · תאריך היתר · מסמכים. העמודה
השלישית נקראה כאן ״תיאור הבקשה״, ו״תמ״א 38״ חופש בה — אבל היא הארוע
**האחרון** (״מסירת היתר למבקש״), ולא מה הבקשה. לכן `strengthened` ו-`occupied`
היו עיוורים: False כמעט תמיד, ועברו כ״לא נמצא״. הם אינם נגזרים מעמוד התיק.
ארוע שכן מזכיר תמ״א 38 או מייצג הוא סימן חיובי אמיתי, ונשמר כבוליאני
(`tama38_event`, `representative_event`) — שם, לעולם לא.

‏**16.09 · דף הבקשה עונה.** לכל בקשה יש דף משלה (`GetBakashaFile`), ובו
״סוג הבקשה״ (״בקשה להיתר לתמ״א 38״), ״תיאור הבקשה״ (״תמ״א 38 - תוספת
וחיזוק״), ״תאריך הפקת היתר״ ו״מהות הבקשה״. אלוף יגאל אלון 6: שתי בקשות
תמ״א 38 עם היתרים מ-2013 ומ-2017 — מה שעמוד התיק הראה כ״מסירת היתר
למבקש״. מכאן `strengthened` (בקשת תמ״א 38 שהופק לה היתר) ו-`occupied`
(בקשת תמ״א 38 שלא הבשילה להיתר) חוזרים, הפעם על מקור שאומר את זה.
נקראים רק דפי הבקשות מ-2005 ואילך — חיזוק מכוח היתר הוא מושג של תמ״א 38
(אושרה 18.5.2005) — ורק עד תקרה; קריאה חלקית אומרת ״כן״ כשמצאה, ולעולם
לא ״לא נמצא״. הדף נחתך לפני ״בעלי עניין״: השמות אינם נקראים.
"""
import argparse
import asyncio
import json
import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select

from app.cities.herzliya import renewal
from app.cities.herzliya.archive_client import ArchiveBlocked, HerzliyaArchiveClient
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

TAG = re.compile(r"<[^>]+>")
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
REQUEST_NO = re.compile(r"^(19|20)\d{6}$")
STRENGTHENING = re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')
# עו״ד מייצג, נציגות, מיופה כוח, ב״כ — בפרויקט התחדשות הבעלים מיוצגים יחד
REPRESENTATIVE = re.compile(r'מייצג|נציג|מיופה[\s-]*כו?ח|ב["״]כ')

MAX_SHORTLIST = 25          # לא סריקה. מעבר לזה — לעצור ולשאול.
# כל תיקי החלקה נקראים (היה: הראשון בלבד — הרצוג 3 הוא 1546 **ו**-7351).
# ‏700 המועמדים הם עד שלושה תיקים לחלקה; חלקה אחת בעיר יש לה 23.
MAX_TIKS = 4

# ── דף הבקשה ──
DETAIL_FROM_YEAR = 2005        # תמ״א 38 אושרה ב-18.5.2005; בקשה ישנה יותר אינה חיזוק מכוחה
MAX_REQUEST_PAGES = 15         # דף לבקשה, בקצב של 10 שניות — עד 2.5 דקות לחלקה
TAMA_TYPE = re.compile(r'תמ["״]?א\s*38')
INFO_ROW = re.compile(r'<td class="title"[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', re.S)
ESSENCE_START = 'id="mahut"'
INTERESTED_PARTIES = 'id="baaley-inyan"'      # מכאן והלאה — שמות. לא נקרא.
REQUEST_FIELDS = ("strengthened", "occupied")
REQUEST_METHOD = "דף הבקשה: סוג הבקשה, תיאורה ותאריך הפקת ההיתר; בעלי העניין אינם נקראים"


class ArchiveUnavailable(Exception):
    """הארכיון לא השיב — ‏CAPTCHA, ‏429, או תקלת רשת.

    **זו אינה תשובה על המועמד.** הגרסה הראשונה החזירה כאן את אותה הודעה
    כמו ״לא נשאל״, והלקוח קרא שלא טרחנו לבדוק — ויצא לחפש את הבעיה
    אצלנו במקום לנסות שוב בעוד חמש דקות.
    """


class NoBuildingFile(Exception):
    """לא נמצא תיק בניין לחלקה. זה **כן** ממצא על המועמד, ואין טעם לנסות שוב."""
CUTOFF_2005 = date(2005, 5, 18)     # §70ב(א)(1)(ב)


def _text(x: str) -> str:
    return TAG.sub("", x).strip()


def parse_requests(page_html: str) -> list[dict[str, Any]]:
    """שורות הבקשות מעמוד תיק. שם המבקש (i+3) אינו נקרא.

    ‏`last_event` הוא ״ארוע אחרון להצגה״ — לא תיאור הבקשה.
    """
    out = []
    for row in ROW.findall(page_html):
        cells = [_text(c) for c in CELL.findall(row)]
        for i, v in enumerate(cells):
            if not REQUEST_NO.match(v or ""):
                continue
            out.append({
                "req": int(v),
                "submitted": cells[i + 1] if len(cells) > i + 1 else None,
                "last_event": cells[i + 2] if len(cells) > i + 2 else None,
                # cells[i + 3] הוא שם המבקש — מדולג בכוונה
                "permit": cells[i + 4] if len(cells) > i + 4 else None,
                "permit_date": cells[i + 5] if len(cells) > i + 5 else None,
            })
            break
    return out


def facts(requests: list[dict[str, Any]]) -> dict[str, Any]:
    """מה שהעמוד עונה עליו. ‏`strengthened`/`occupied` אינם כאן — ראו למעלה."""
    years = [int(str(r["req"])[:4]) for r in requests if str(r.get("req", ""))[:4].isdigit()]
    return {
        "earliest_year": min(years) if years else None,
        "permit_date": f"{min(years)}-01-01" if years else None,
        # §70ב(א)(1)(ב): תוספת שהותרה אחרי המועד אינה נכנסת לבסיס ה-400%.
        # התיק מדווח שהיתר ניתן, לא כמה מ״ר הוא הוסיף — ולכן בוליאני.
        "post_2005_permit": _post_2005(requests),
        # סימנים חיוביים בלבד: ארוע שמזכיר — כן; היעדרו — אינו אומר דבר
        "tama38_event": any(STRENGTHENING.search(r.get("last_event") or "") for r in requests),
        "representative_event": any(REPRESENTATIVE.search(r.get("last_event") or "")
                                    for r in requests),
        "n_requests": len(requests),
    }


def parse_request_page(page_html: str) -> dict[str, Any]:
    """סוג, תיאור, היתר ומהות מדף בקשה. הדף נחתך לפני ״בעלי עניין״.

    ‏`tama38` — הסיווג העירוני: סוג הבקשה או תיאורה. ‏`mentions` רחב יותר
    (גם המהות) ומזין רק את סימן החידוש, כי תיקון תשריט ״בהתאם לתמ״א 38״
    מעיד על בניין שחודש ולא על בקשת חיזוק.
    """
    head = page_html.split(INTERESTED_PARTIES, 1)[0]
    info = {_text(k): _text(v) for k, v in INFO_ROW.findall(head)}
    essence_html = head.split(ESSENCE_START, 1)[1] if ESSENCE_START in head else ""
    essence = " ".join(_text(c) for c in CELL.findall(essence_html))
    kind, desc = info.get("סוג הבקשה") or "", info.get("תיאור הבקשה") or ""
    return {
        "type": kind,
        "description": desc,
        "permit_date": info.get("תאריך הפקת היתר") or None,
        "tama38": bool(TAMA_TYPE.search(kind) or STRENGTHENING.search(desc)),
        "mentions": bool(STRENGTHENING.search(" ".join((kind, desc, essence)))),
    }


def request_facts(details: list[dict[str, Any]], complete: bool = True) -> dict[str, Any]:
    """‏§70א(2) ו״יזם אחר בתמונה״ מדפי הבקשות שנקראו.

    ‏`complete` — האם כל בקשות החלקה מ-2005 ואילך נקראו. אמת מקריאה חלקית
    היא אמת; ״לא נמצא״ נאמר רק כשנקרא הכול.
    """
    tama = [d for d in details if d.get("tama38")]
    permitted = [d for d in tama if d.get("permit_date")]
    open_ = [d for d in tama if not d.get("permit_date")]

    def verdict(found: bool) -> bool | None:
        return True if found else (False if complete else None)

    return {
        "strengthened": verdict(bool(permitted)),
        "occupied": verdict(bool(open_)),
        "tama38_mention": any(d.get("mentions") for d in details),
        "strengthening_permits": [(d.get("req"), d["permit_date"]) for d in permitted],
        "open_tama_requests": [d.get("req") for d in open_],
    }


async def _request_details(client, reqs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """דפי הבקשות מ-2005 ואילך, עד התקרה. מחזיר גם האם נקראו כולם."""
    recent = sorted({int(r["req"]) for r in reqs
                     if int(str(r["req"])[:4]) >= DETAIL_FROM_YEAR}, reverse=True)
    details = []
    for n in recent[:MAX_REQUEST_PAGES]:
        page = await client.request(str(n))
        details.append({**parse_request_page(page["html"]), "req": n})
    return details, len(recent) <= MAX_REQUEST_PAGES


def _post_2005(requests) -> bool:
    for r in requests:
        try:
            d, m, y = (int(x) for x in (r.get("permit_date") or "").strip().split("/"))
            if date(y, m, d) > CUTOFF_2005:
                return True
        except ValueError:
            continue
    return False


async def enrich(session, opportunity_ids: list[UUID], client: HerzliyaArchiveClient | None = None) -> dict:
    """מביא את כל תיקי החלקה לכל הזדמנות ברשימה, כותב את העובדות כראיה,
    ומעדכן מולן את `renewal_status`."""
    if len(opportunity_ids) > MAX_SHORTLIST:
        raise ValueError(
            f"‏{len(opportunity_ids)} הזדמנויות — מעל {MAX_SHORTLIST}. "
            "הארכיון אינו מיועד לסריקה; יש לצמצם לרשימה קצרה."
        )
    own = client is None
    client = client or HerzliyaArchiveClient()
    # ‏`empty` הופרד מ-`failed`: עמוד תיק שנמשך בהצלחה ואין בו שורות בקשה
    # אינו תקלת תקשורת אלא **ממצא על החלקה**. הן נספרו יחד, ולכן תיק ריק
    # דווח ללקוח כ״הארכיון לא השיב, נסה שוב״ — והוא היה מנסה לנצח.
    result = {"fetched": 0, "no_tik": 0, "empty": 0, "failed": 0,
              "requests": 0, "last_error": None, "blocked": False}
    try:
        for oid in opportunity_ids:
            opp = await session.get(Opportunity, oid)
            if not opp or not opp.block or not opp.parcel:
                result["no_tik"] += 1
                continue
            try:
                tik_ids = await client.find_tik_ids(opp.block, opp.parcel)
                if not tik_ids:
                    result["no_tik"] += 1
                    continue
                pages = [await client.file(t) for t in tik_ids[:MAX_TIKS]]
                reqs = [r for page in pages for r in parse_requests(page["html"])]
                if not reqs:
                    result["empty"] += 1
                    continue
                f = facts(reqs)
                if len(tik_ids) > MAX_TIKS:
                    # לא נקרא הכול — ״אין היתר אחרי 2005״ אינו ידוע
                    f["post_2005_permit"] = f["post_2005_permit"] or None
                details, all_read = await _request_details(client, reqs)
                rf = request_facts(details, complete=all_read and len(tik_ids) <= MAX_TIKS)
                f.update(strengthened=rf["strengthened"], occupied=rf["occupied"],
                         tama38_event=f["tama38_event"] or rf["tama38_mention"],
                         request_pages=len(details),
                         strengthening_permits=rf["strengthening_permits"],
                         open_tama_requests=rf["open_tama_requests"])
                await _write(session, oid, f, pages[0], tik_ids[:MAX_TIKS], len(tik_ids))
                await renewal.apply(session, opp)
                result["fetched"] += 1
                result["requests"] += len(reqs)
            except ArchiveBlocked as exc:
                # סירוב אינו תקלה בתיק אחד: כל בקשה נוספת רק מאריכה את החסימה.
                # החלקות שלא נשאלו נספרות כנכשלות — ״נסה שוב״, לא ״אין תיק״.
                result["failed"] += len(opportunity_ids) - sum(
                    result[k] for k in ("fetched", "no_tik", "empty", "failed"))
                result["blocked"] = True
                result["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
                break
            except Exception as exc:                # תקלה בתיק אחד אינה מפילה את השאר
                result["failed"] += 1
                # הסיבה נשמרת: במסלול המסירה היא ההבדל בין ״נסה שוב״
                # לבין ״אין מה לעשות״, ובלעדיה שתיהן נראות אותו דבר.
                result["last_error"] = f"{type(exc).__name__}: {exc}"[:200]
        # ‏flush ולא commit: הבעלות על הטרנזקציה היא של הקורא. במסלול
        # המסירה השליפה, ההערכה מחדש והמסירה חייבות להיות עסקה אחת —
        # commit כאן היה מקבע תיק שנשלף גם אם המסירה נכשלה אחריו.
        await session.flush()
    finally:
        if own:
            await client.close()
    return result


async def _write(session, oid: UUID, f: dict, page: dict, tik_ids: list[str],
                 total: int | None = None) -> None:
    src = page.get("source") or {}
    url = src.get("url") or "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
    when = src.get("retrieved_at")
    when = datetime.fromisoformat(when) if isinstance(when, str) else datetime.now(timezone.utc)
    tiks = ", ".join(tik_ids)
    read = f" (נקראו {len(tik_ids)} מתוך {total})" if total and total > len(tik_ids) else ""
    loc = f'{"תיקים" if len(tik_ids) > 1 else "תיק"} {tiks}{read} · {f["n_requests"]} בקשות'
    # מה שדף הבקשה קבע — מספרי בקשה ותאריכי היתר, לא שמות
    found = [f"בקשת תמ״א 38 {n} · היתר {d}" for n, d in f.get("strengthening_permits") or []]
    found += [f"בקשת תמ״א 38 {n} ללא היתר" for n in f.get("open_tama_requests") or []]
    pages = f.get("request_pages")
    req_loc = (loc + (f" · {pages} דפי בקשה" if pages is not None else "")
               + (" · " + " · ".join(found) if found else ""))

    # שורות עיוורות (W5): ‏`strengthened`/`occupied` שנגזרו מ״ארוע אחרון להצגה״
    # ולא מדף הבקשה. נמחקות תמיד — גם כשהקריאה הזו לא הכריעה.
    await session.execute(delete(FieldEvidence).where(
        FieldEvidence.opportunity_id == oid, FieldEvidence.field.in_(REQUEST_FIELDS),
        or_(FieldEvidence.method.is_(None), FieldEvidence.method != REQUEST_METHOD)))
    for field in ARCHIVE_FIELDS:
        value = f.get(field)
        if value is None:
            continue
        await session.execute(
            delete(FieldEvidence).where(FieldEvidence.opportunity_id == oid,
                                        FieldEvidence.field == field))
        from_request = field in REQUEST_FIELDS
        session.add(FieldEvidence(
            opportunity_id=oid, field=field, value=value,
            certainty=Certainty.DERIVED.value, source_url=url, retrieved_at=when,
            location=req_loc if from_request else loc,
            method=REQUEST_METHOD if from_request else
            "שורות הבקשות בתיק הבניין; שם המבקש אינו נקרא"))


# השערים שתיק הבניין יכול לענות עליהם. שער פתוח שאינו כאן — אין טעם
# לפנות לארכיון בשבילו, וכל פנייה מיותרת היא בדיוק מה שהפעיל את ההגנה
# ב-12.09. ‏`strengthened`/`occupied` יצאו (W5) וחזרו ב-16.09 — מדף הבקשה.
ARCHIVE_ANSWERS = frozenset({"permit_date", "post_2005_permit", "not_renewed",
                             "strengthened", "occupied"})


async def fetch_for_delivery(session, opportunity_id: UUID, client=None) -> bool:
    """שליפת תיק אחד ברגע שלקוח מבקש את החלקה. מחזיר האם משהו השתנה.

    זו הלולאה שהייתה פתוחה: ‏`deliver()` סירב למועמד שתנאי הסף שלו לא
    נשאל, ושום דבר לא שאל. עכשיו **רגע המסירה הוא רגע השליפה** — חלקה
    אחת, לפי בקשה מפורשת של לקוח, ונשמרת לתמיד. זה בדיוק המטמון שמרשם
    הסיכון מחייב, להבדיל מהסריקה היזומה שהארכיון חסם.

    אם השער הפתוח אינו כזה שהתיק עונה עליו — לא נשלחת בקשה בכלל.
    """
    from app.cities.herzliya.assessments import refresh_one
    from app.cities.herzliya.rules import HerzliyaCityRules

    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        return False
    assessment = (opp.metadata_json or {}).get("assessment") or {}
    # ‏`threshold_open` בלבד: ‏`blocking` כולל גם רוחב רחוב וקטגוריה, שאין
    # לתיק הבניין מה לומר עליהם, ופנייה בשבילם היא בקשה מיותרת.
    open_gates = set(assessment.get("threshold_open") or []) & ARCHIVE_ANSWERS
    if not open_gates:
        return False
    if open_gates == {"not_renewed"}:
        # התיק כבר נקרא, ורק ההכרעה על החידוש חסרה — נגזרת מהמסד, בלי פנייה
        if (await renewal.apply(session, opp))["status"] != "unknown":
            await refresh_one(session, HerzliyaCityRules(), opportunity_id)
            return True

    out = await enrich(session, [opportunity_id], client)
    if out.get("no_tik"):
        raise NoBuildingFile(
            "לא נמצא תיק בניין לחלקה זו בארכיון העירוני. "
            "מועד ההיתר והיסטוריית החיזוק אינם ניתנים לאימות ממקור אחר."
        )
    if out.get("empty"):
        raise NoBuildingFile(
            "תיק הבניין נמצא ואין בו שורות בקשה. מועד ההיתר והיסטוריית "
            "החיזוק אינם ניתנים לאימות ממנו."
        )
    if out.get("failed") or not out.get("fetched"):
        raise ArchiveUnavailable(
            "הארכיון העירוני לא השיב כרגע. הבקשה לא בוצעה ולא נוכתה זכאות — "
            "אפשר לנסות שוב בעוד כמה דקות."
        )
    await refresh_one(session, HerzliyaCityRules(), opportunity_id)
    return True


# ── שחזור: מה שנשלף חי חייב לשרוד מכונה חדשה ──

FETCHED_FILE = "archive_fetched.json"

# השדות שמקורם בתיק הבניין, וששווה לשמור בגיט. כולם **עובדות נגזרות** —
# מותר לשמור אותן ללא הגבלה לפי `DATA_LAW.md`. ‏HTML גולמי, שמות מבקשים
# וחתימות אינם כאן ולא יהיו.
ARCHIVE_FIELDS = ("permit_date", "post_2005_permit", "tama38_event", "representative_event",
                  *REQUEST_FIELDS)


async def export_fetched(session, city_code: str = "herzliya") -> dict:
    """כותב את ראיות הארכיון שבמסד לקובץ, לפי גוש/חלקה.

    שליפת תיק עולה לנו: היא מוגבלת בקצב, והמדיניות מחייבת לשמור אותה
    **לתמיד**. אבל היא נכתבה עד כה למסד בלבד — כלומר חיה על מכונה אחת.
    מכונה חדשה שתזרע מאפס תקבל רק את מה שבקובץ הישן, ומספר המועמדים
    המוכנים יירד בלי הסבר. זה קרה: ‏9 ירדו ל-5.
    """
    from sqlalchemy import select

    rows = (await session.execute(
        select(Opportunity.block, Opportunity.parcel, FieldEvidence)
        .join(FieldEvidence, FieldEvidence.opportunity_id == Opportunity.id)
        .where(Opportunity.city_code == city_code,
               FieldEvidence.field.in_(ARCHIVE_FIELDS),
               FieldEvidence.source_url.like("%complot%"))
    )).all()

    out: dict[str, dict] = {}
    for block, parcel, ev in rows:
        entry = out.setdefault(f"{block}/{parcel}", {"fields": {}})
        entry["fields"][ev.field] = ev.value
        entry.setdefault("source_url", ev.source_url)
        entry.setdefault("location", ev.location)
        if ev.field not in REQUEST_FIELDS:      # לשדות דף הבקשה שיטה משלהם, והזורע יודע
            entry.setdefault("method", ev.method)
        stamp = ev.retrieved_at.isoformat() if ev.retrieved_at else None
        if stamp and stamp > entry.get("retrieved_at", ""):
            entry["retrieved_at"] = stamp

    # אותו שורש שהזורע משתמש בו, כדי ששניהם לא יסטו.
    from app.cities.herzliya.seed_layer_a import LAYER_A

    path = LAYER_A / FETCHED_FILE
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    return {"parcels": len(out), "path": str(path)}


async def _main(argv=None):
    """‏`enrich()` נכתב ולא הייתה לו דרך הרצה, ולכן גם לא רצה מעולם על
    הזדמנות אמיתית. הרשימה הקצרה נמסרת במפורש — אין כאן ״כל העיר״."""
    from app.core.database import AsyncSessionLocal
    ap = argparse.ArgumentParser(description="העשרה מתיקי הבניין, וייצוא לשחזור")
    ap.add_argument("ids", nargs="*", help=f"מזהי הזדמנות · עד {MAX_SHORTLIST}")
    ap.add_argument("--export", action="store_true",
                    help="כתיבת ראיות הארכיון שבמסד לקובץ, כדי שזריעה חדשה תשחזר אותן")
    a = ap.parse_args(argv)
    async with AsyncSessionLocal() as session:
        if a.export:
            return await export_fetched(session)
        if not a.ids:
            ap.error("יש לציין מזהי הזדמנות, או --export")
        out = await enrich(session, [UUID(x) for x in a.ids])
        await session.commit()
    return out


if __name__ == "__main__":
    print(asyncio.run(_main()))
