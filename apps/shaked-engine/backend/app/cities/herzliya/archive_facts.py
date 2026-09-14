"""שני השערים שרק הארכיון יכול לענות עליהם, ורק לרשימה קצרה.

‏§70א(2) שואל אם המבנה **חוזק בהיתר** — ואם כן הוא פסול. ושאלה מסחרית
נפרדת היא אם **יזם אחר כבר בתמונה**: בקשת חיזוק שהוגשה ולא הבשילה להיתר.
שתיהן קיימות רק בתיק הבניין, ולכן לא ניתן להעריך אותן משום מקור אחר.

**המודול הזה אינו סורק.** הוא מקבל רשימת הזדמנויות ומביא תיק לכל אחת,
כי הארכיון עונה לפרצי בקשות ב-429 ובחלק מהמקרים ב-CAPTCHA. התבנית שנקבעה
בארכיטקטורה היא זולה על 700 ויקרה על עשר — והמגבלה כאן אוכפת אותה.

**פרטיות:** עמודת שם המבקש היא `i+3` בשורת הבקשה, והיא מדולגת **בזמן
הפרסור** ולא מסוננת אחר כך. שם שלא נקרא אינו יכול להישמר בטעות.
"""
import argparse
import asyncio
import json
import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.cities.herzliya.archive_client import HerzliyaArchiveClient
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

TAG = re.compile(r"<[^>]+>")
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
REQUEST_NO = re.compile(r"^(19|20)\d{6}$")
STRENGTHENING = re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')

MAX_SHORTLIST = 25          # לא סריקה. מעבר לזה — לעצור ולשאול.


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
    """שורות הבקשות מעמוד תיק. שם המבקש (i+3) אינו נקרא."""
    out = []
    for row in ROW.findall(page_html):
        cells = [_text(c) for c in CELL.findall(row)]
        for i, v in enumerate(cells):
            if not REQUEST_NO.match(v or ""):
                continue
            out.append({
                "req": int(v),
                "submitted": cells[i + 1] if len(cells) > i + 1 else None,
                "action": cells[i + 2] if len(cells) > i + 2 else None,
                # cells[i + 3] הוא שם המבקש — מדולג בכוונה
                "permit": cells[i + 4] if len(cells) > i + 4 else None,
                "permit_date": cells[i + 5] if len(cells) > i + 5 else None,
            })
            break
    return out


def facts(requests: list[dict[str, Any]]) -> dict[str, Any]:
    """מבקשות לשני השערים. `occupied` ו-`strengthened` אינם אותו דבר."""
    years = [int(str(r["req"])[:4]) for r in requests if str(r.get("req", ""))[:4].isdigit()]
    hits = [r for r in requests if STRENGTHENING.search(r.get("action") or "")]
    return {
        "earliest_year": min(years) if years else None,
        "permit_date": f"{min(years)}-01-01" if years else None,
        # חיזוק שהופק לו היתר → פסול לפי §70א(2)
        "strengthened": any((r.get("permit_date") or "").strip() for r in hits),
        # בקשת חיזוק ללא היתר → יזם אחר מול הדיירים. כשיר בדין, לא זמין בפועל.
        "occupied": any(not (r.get("permit_date") or "").strip() for r in hits),
        # §70ב(א)(1)(ב): תוספת שהותרה אחרי המועד אינה נכנסת לבסיס ה-400%.
        # התיק מדווח שהיתר ניתן, לא כמה מ״ר הוא הוסיף — ולכן בוליאני.
        "post_2005_permit": _post_2005(requests),
        "n_requests": len(requests),
    }


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
    """מביא תיק לכל הזדמנות ברשימה וכותב את שני השערים כראיה."""
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
              "requests": 0, "last_error": None}
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
                page = await client.file(tik_ids[0])
                reqs = parse_requests(page["html"])
                if not reqs:
                    result["empty"] += 1
                    continue
                f = facts(reqs)
                await _write(session, oid, f, page, tik_ids[0])
                result["fetched"] += 1
                result["requests"] += len(reqs)
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


async def _write(session, oid: UUID, f: dict, page: dict, tik_id: str) -> None:
    src = page.get("source") or {}
    url = src.get("url") or "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
    when = src.get("retrieved_at")
    when = datetime.fromisoformat(when) if isinstance(when, str) else datetime.now(timezone.utc)
    loc = f'תיק {tik_id} · {f["n_requests"]} בקשות'

    for field, value in (("permit_date", f["permit_date"]),
                         ("strengthened", f["strengthened"]),
                         ("occupied", f["occupied"]),
                         ("post_2005_permit", f["post_2005_permit"])):
        if value is None:
            continue
        await session.execute(
            delete(FieldEvidence).where(FieldEvidence.opportunity_id == oid,
                                        FieldEvidence.field == field))
        session.add(FieldEvidence(
            opportunity_id=oid, field=field, value=value,
            certainty=Certainty.DERIVED.value, source_url=url, retrieved_at=when,
            location=loc, method="שורות הבקשות בתיק הבניין; שם המבקש אינו נקרא"))


# השערים שתיק הבניין יכול לענות עליהם. שער פתוח שאינו כאן — אין טעם
# לפנות לארכיון בשבילו, וכל פנייה מיותרת היא בדיוק מה שהפעיל את ההגנה
# ב-12.09.
ARCHIVE_ANSWERS = frozenset({"permit_date", "strengthened", "occupied", "post_2005_permit"})


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
    open_gates = set(assessment.get("threshold_open") or [])
    if not (open_gates & ARCHIVE_ANSWERS):
        return False

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
ARCHIVE_FIELDS = ("permit_date", "strengthened", "occupied", "post_2005_permit")


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
