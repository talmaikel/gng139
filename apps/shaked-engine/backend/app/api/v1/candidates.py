import time
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities import get_city_rules as _get_city_rules
from app.core.database import get_async_session
from app.core.security import current_active_user, current_superuser
from app.models.tenant import User
from app.cities.herzliya.archive_facts import (ArchiveUnavailable, NoBuildingFile,
                                               fetch_for_delivery)
from app.cities.herzliya import exports
from app.cities.herzliya.dossier import NotEntitled, build as build_dossier, screening
from app.services.economic.assumptions import get_assumptions
from app.services.deliveries import (NoCredits, NotDeliverable, _credits, deliver,
                                     delivered_ids, for_company, held_for_renewal,
                                     provenance)

router = APIRouter(prefix="/candidates", tags=["candidates"])


def get_city_rules(city_code: str):
    """‏`ValueError` על עיר לא רשומה הגיע ללקוח כ-500 — שגיאת שרת על קלט
    של משתמש. עיר שאינה קיימת היא 404."""
    try:
        return _get_city_rules(city_code)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


class Preference(BaseModel):
    """העדפת מיון אחת. ‏PRD 4.2: היזם מגדיר סדר מפורש, לא משקולות."""
    field: Literal["parcel_area", "units", "floors", "cap_400"]
    direction: Literal["asc", "desc"] = "desc"


class SearchArea(BaseModel):
    """אזור חיפוש מצויר, GeoJSON Polygon ב-WGS84, עם תנאי חובה וסדר העדפות.

    **תנאי חובה מוציאים מהרשימה; העדפות רק מסדרות אותה.** ה-PRD מפריד
    ביניהם (SEL-01), ולכן גם הבקשה מפרידה — מינימום שנשלח כהעדפה היה
    מדרג נמוך מועמד שהיזם כלל אינו רוצה לראות.
    """
    polygon: dict[str, Any]
    # ── תנאי חובה ──
    min_area_sqm: float | None = Field(default=None, ge=0)
    min_units: int | None = Field(default=None, ge=0)
    min_floors: float | None = Field(default=None, ge=0)
    min_cap_400_sqm: float | None = Field(default=None, ge=0)
    certain_floors_only: bool = False
    deliverable_only: bool = False
    # שלוש לכל היותר — מעבר לכך הסדר מפסיק להיות מובן למי שהגדיר אותו.
    preferences: list[Preference] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=100, le=500)


# ‏#89 · **הרשימה המלאה היא לצוות בלבד.** הלקוח מקבל תיקים דרך הסריקה
# (`scan/preview`, `scan/deliver`) ואינו רואה מועמדים (בועז, 15.09): רשימה
# עם כתובות ממוינות היא המוצר עצמו בחינם. שני הנתיבים האלה משרתים את מסך
# הצוות ‏/admin/candidates, ולכן superuser בלבד.
@router.post("/{city_code}/search")
async def search_candidates(
    city_code: str,
    body: SearchArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_superuser),
) -> list[dict[str, Any]]:
    """מועמדים בתוך אזור מצויר — מסך הצוות. פוליגון שאינו תקין או חורג מהעיר נדחה ב-422."""
    rules = get_city_rules(city_code)
    filters = body.model_dump()
    # מה שכבר נמסר לחברה אינו מוצע שוב כהזדמנות חדשה — הוא נשאר במאגר שלה.
    filters["exclude_delivered_ids"] = await delivered_ids(session, user.company_id)
    try:
        return await rules.screen_candidates(session, filters)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


# ── S1 · סריקה: פוליגון → עד שלושה תיקים, בלי לחשוף מועמדים ──
#
# ‏**הלקוח אינו רואה מועמדים** (בועז, 15.09). רשימה מלאה עם כתובות היא
# המוצר עצמו בחינם: מי שרואה 23 כתובות ממוינות לפי תקרת 400% אינו צריך
# לקנות את שלוש הראשונות. הסריקה מחזירה מספר לפני החיוב, ותיקים אחריו.

SCAN_SIZE = 3
# שליפה מהארכיון היא 10–20 שניות, והדפדפן ממתין עד 90. אחרי התקציב לא
# מתחילים שליפה חדשה: מחזירים ``more``, והמסך קורא שוב עם מה שנשאר (טל, 16.09).
SCAN_TIME_BUDGET_S = 60.0


class ScanArea(BaseModel):
    """האזור והתנאים של הלקוח. **הסריקה קובעת כמה** — לפי היתרה — **ובאיזה סדר.**

    ‏**W6 · בועז, 16.09:** ללקוח שלושה תנאים — גודל מגרש, רווח יזמי מזערי ומקסימום
    דירות קיימות — ובלי סדר העדפות. שלושת התיקים הם הרווחיים ביותר, לפי הרווח
    אחרי אומדן היטל על השטח שמותר לפי מדיניות הרצליה.
    """
    polygon: dict[str, Any]
    min_area_sqm: float | None = Field(default=None, ge=0)
    max_units: int | None = Field(default=None, ge=0)
    # ברירת המחדל היא הרווח היזמי המזערי בספריית ההנחות (16%).
    min_profit_ratio: float | None = Field(default=None, ge=0, le=1)
    # חלקה שכלכלית רק עם הגדלת זכויות נמסרת רק בסימון, ואחרי הכלכליות.
    include_rights_request: bool = False
    # ‏כשאין אף חלקה כלכלית, הלקוח מאשר לפני שכתובת נחשפת (בועז, 16.09).
    accept_rights_request: bool = False
    # ‏״תיקים מושלמים״ (טל, 16.09): רק מגרשים שתיק הבניין שלהם כבר שלם. בלי
    # שליפה מהארכיון בזמן החיפוש — התוצאה מיידית, ואין תיק שנשלף חלקית.
    ready_only: bool = False
    # ‏המשך אוטומטי של אותה סריקה: כמה תיקים עוד חסרים, ומה כבר נבדק ונפל
    # בקריאה קודמת — ‏`NoBuildingFile` אינו נשמר, ובלעדיו ההמשך היה שולף שוב.
    want: int | None = Field(default=None, ge=1, le=SCAN_SIZE)
    skip_ids: list[UUID] = Field(default_factory=list, max_length=200)
    # ‏W6 · נשארו עד שמסך הסריקה יורד מהם. **אינם משפיעים על הסריקה** — הם
    # תנאי צוות, ונשארים ב-`/search` של המנהל.
    min_units: int | None = Field(default=None, ge=0)
    min_floors: float | None = Field(default=None, ge=0)
    min_cap_400_sqm: float | None = Field(default=None, ge=0)
    certain_floors_only: bool = False
    preferences: list[Preference] = Field(default_factory=list, max_length=3)


def _ready(row: dict[str, Any]) -> bool:
    return bool((row.get("assessment") or {}).get("deliverable"))


# נקודת החלפה לבדיקות: הכלכלה של מועמד אחד, מאותו חישוב כמו התיק.
parcel_economics = screening


async def _scan_queue(session, rules, body: ScanArea, company_id) -> dict[str, list[dict[str, Any]]]:
    """שני תורים: **כלכליות** לפי המדיניות, ו**כלכליות רק עם הגדלת זכויות**.

    בכל תור — שכבת הביטחון קודם (‏scan.html rev 35), ובתוכה הרווחיות קודם.
    המוכנות אינה משנה את הסדר (טל, 16.09): מגרש חזק שעוד לא נשלף נבדק ראשון.
    חלקה שאינה כלכלית גם בתקרת ה-400%, או שאין לה תרחיש, אינה מוצעת כלל:
    אין בה הזדמנות, והלקוח לא ישלם עליה.
    """
    filters = {"polygon": body.polygon, "min_area_sqm": body.min_area_sqm,
               "max_units": body.max_units, "limit": 500,
               "exclude_delivered_ids": await delivered_ids(session, company_id) | set(body.skip_ids)}
    try:
        rows = await rules.screen_candidates(session, filters)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    # ‏W5 · מחודש או חשוד — לא בתור כלל. לא נספר ב-``found``, לא נשלף ולא מחויב.
    in_track = [r for r in rows
                if not held_for_renewal(r.get("assessment"))
                and (_ready(r) or (r.get("assessment") or {}).get("screenable"))]
    if body.ready_only:
        in_track = [r for r in in_track if _ready(r)]

    threshold = (body.min_profit_ratio if body.min_profit_ratio is not None
                 else get_assumptions(rules.city_code).developer_profit_target_ratio.value)
    economic, rights = [], []
    for r in in_track:
        e = await parcel_economics(session, rules, UUID(r["id"]))
        r["economics"] = e
        if e.get("margin") is not None and e["margin"] >= threshold:
            economic.append(r)
        elif e.get("cap_margin") is not None and e["cap_margin"] >= threshold:
            rights.append(r)
    economic.sort(key=lambda r: (r["economics"].get("tier", 2), -r["economics"]["margin"]))
    rights.sort(key=lambda r: (r["economics"].get("tier", 2), -r["economics"]["cap_margin"]))
    return {"economic": economic, "rights": rights}


def _offered(q: dict[str, list], body: ScanArea) -> list[dict[str, Any]]:
    """מה שייצא, בסדר: כלכליות, ואחריהן חלקות הגדלת זכויות — רק בסימון, ואם אין
    כלכליות כלל, רק אחרי אישור."""
    if not body.include_rights_request:
        return q["economic"]
    if not q["economic"] and not body.accept_rights_request:
        return []
    return q["economic"] + q["rights"]


def _needs_confirmation(q: dict[str, list], body: ScanArea) -> dict[str, int] | None:
    if body.include_rights_request and not body.accept_rights_request \
            and not q["economic"] and q["rights"]:
        return {"count": len(q["rights"])}
    return None


@router.post("/{city_code}/scan/preview")
async def scan_preview(
    city_code: str,
    body: ScanArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """כמה יימסרו, לפני החיוב. **מספרים בלבד** — בלי כתובת, מזהה או גאומטריה."""
    rules = get_city_rules(city_code)
    q = await _scan_queue(session, rules, body, user.company_id)
    queue = _offered(q, body)
    credits = await _credits(session, user.company_id)
    offer = min(SCAN_SIZE, credits, len(queue))
    ready = sum(1 for r in queue[:offer] if _ready(r))
    return {"found": len(queue), "offer": offer, "ready": ready,
            "needs_fetch": offer - ready, "credits_remaining": credits,
            "found_economic": len(q["economic"]), "found_rights_request": len(q["rights"]),
            "needs_rights_confirmation": _needs_confirmation(q, body)}


@router.post("/{city_code}/scan/deliver")
async def scan_deliver(
    city_code: str,
    body: ScanArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """מוסר עד שלושה מגרשים מהאזור, לפי סדר `_scan_queue`, **אחד-אחד**.

    מגרש שלא נשלף עדיין — שולפים אותו עכשיו, מעריכים מחדש, ומוסרים רק אם
    עבר את תנאי הסף. אחרי ``SCAN_TIME_BUDGET_S`` לא מתחילים שליפה חדשה
    ומחזירים ``more``; המסך ממשיך עם ``want`` ו-``skip_ids``.

    מגרש שאין לו תיק בניין או שהשליפה לא ענתה על השער — מדלגים לבא אחריו,
    ואינו מחויב (ACC-05). ארכיון שסירב — עוצרים ומחזירים `retryable`:
    קריאה חוזרת משלימה, כי מה שכבר נמסר אינו מוצע שוב. כל מסירה נשמרת
    מיד, כך שבקשה שנקטעה באמצע אינה מאבדת את מה שכבר נמסר.

    ‏**W6 · אין אף חלקה כלכלית, והלקוח סימן הגדלת זכויות:** מוחזר
    `needs_rights_confirmation` — מספר בלבד, בלי חיוב ובלי כתובת — והמסירה
    קורית רק בקריאה חוזרת עם `accept_rights_request`.
    """
    rules = get_city_rules(city_code)
    # ‏rollback על מגרש שדולג מפקיע את כל האובייקטים בסשן, כולל המשתמש;
    # קריאה של `user.company_id` אחריו הייתה פונה למסד מחוץ להקשר האסינכרוני.
    company_id, user_id = user.company_id, user.id
    credits = await _credits(session, company_id)
    if credits < 1:
        raise HTTPException(status_code=402, detail="לא נותרה זכאות לחברה. יש לרכוש חבילה כדי להמשיך.")
    q = await _scan_queue(session, rules, body, company_id)
    counts = {"found_economic": len(q["economic"]), "found_rights_request": len(q["rights"])}
    if (confirm := _needs_confirmation(q, body)) is not None:
        return {"delivered": [], "found": 0, "requested": 0, "skipped": 0, "retryable": False,
                "message": None, "credits_remaining": credits, **counts,
                "skipped_ids": [], "checked": 0, "more": False,
                "needs_rights_confirmation": confirm}
    queue = _offered(q, body)
    target = min(body.want or SCAN_SIZE, credits)
    started = time.monotonic()
    # ‏16.09 · מאיזה תור הגיע כל תיק — כלכלי לפי המדיניות, או רק עם הגדלת זכויות.
    # נשמר עם המסירה, כי המסך מסמן את השניים בצבע ובכותרת, וגם ״התיקים שלי״.
    track_of = ({r["id"]: "economic" for r in q["economic"]}
                | {r["id"]: "rights_request" for r in q["rights"]})

    async def prepare(s, oid):
        return await fetch_for_delivery(s, oid)

    delivered: list[str] = []
    skipped_ids: list[str] = []
    checked, more, retryable, message = 0, False, False, None
    for candidate in queue:
        if len(delivered) >= target:
            break
        if not _ready(candidate) and time.monotonic() - started >= SCAN_TIME_BUDGET_S:
            more = True
            break
        checked += 1
        oid = UUID(candidate["id"])
        try:
            row, charged = await deliver(session, oid, company_id, user_id,
                                         on_unready=prepare)
            if charged:
                p = await provenance(session, oid)
                e = candidate.get("economics") or {}
                row.rules_version, row.data_version, row.why_selected = (
                    p["rules_version"], p["data_version"],
                    {**p["why"], "track": track_of.get(candidate["id"]),
                     "case": e.get("case"), "margin": e.get("margin"),
                     "cap_margin": e.get("cap_margin")})
                await session.flush()
            await session.commit()
            if charged:
                delivered.append(str(oid))
        except (NoBuildingFile, NotDeliverable):
            await session.rollback()
            skipped_ids.append(str(oid))
        except ArchiveUnavailable:
            await session.rollback()
            retryable = True
            message = "ארכיון העירייה לא ענה כרגע. אפשר לנסות שוב בעוד כמה דקות — לא חויבת על מה שלא נמסר."
            break
        except NoCredits:
            await session.rollback()
            break

    mine = {m["opportunity_id"]: m for m in await for_company(session, company_id)}
    return {
        "delivered": [mine[i] for i in delivered if i in mine],
        # כמה מועמדים היו באזור בכלל: 0 הוא ״אין הזדמנויות כאן״, לא ״נכשל״.
        "found": len(queue),
        "requested": target,
        "skipped": len(skipped_ids),
        "skipped_ids": skipped_ids,
        "checked": checked,
        "more": more,
        "retryable": retryable,
        "message": message,
        "credits_remaining": await _credits(session, company_id),
        **counts,
        "needs_rights_confirmation": None,
    }


@router.get("/{city_code}/mine")
async def my_deliveries(
    city_code: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """מאגר המסירות של החברה — ‏SEL-02: *״מוצג במאגר החברה בלבד״*."""
    get_city_rules(city_code)
    return await for_company(session, user.company_id)


@router.get("/{city_code}/{opportunity_id}/dossier")
async def get_dossier(
    city_code: str,
    opportunity_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """התיק המלא — שרשרת 1–9, ראיות, תרחיש ופערים. רק למי שקיבל אותו.

    ‏**404 ולא 403.** ‏ACC-08: *״בקשה של חברה ללא הרשאה לתיק נדחית גם
    כשמזהה התיק ידוע״* — ו-403 מאשר שהמזהה קיים, וזו דליפה בפני עצמה.
    """
    rules = get_city_rules(city_code)
    try:
        return await build_dossier(session, rules, opportunity_id, user.company_id)
    except NotEntitled as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ‏DOS-04: *״ייצוא PDF של התיק ו-Excel של נתוני התרחיש נכללים בגרסה
# הראשונה״*. שני הנתיבים עוברים דרך אותה בדיקת בעלות כמו התיק עצמו —
# ‏ACC-08 אומר במפורש שחלקה אינה נמסרת ״דרך צמד, קישור, **ייצוא**, מטמון
# או API״, וייצוא שעוקף את הבדיקה הוא בדיוק הדלת האחורית הזו.
EXPORTS = {
    "pdf": (exports.pdf, "application/pdf"),
    "xlsx": (exports.excel,
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


@router.get("/{city_code}/{opportunity_id}/dossier.{fmt}")
async def export_dossier(
    city_code: str,
    opportunity_id: UUID,
    fmt: str,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> Response:
    """התיק כקובץ. ‏`pdf` למסמך, ‏`xlsx` לתרחיש עם נוסחאות חיות."""
    if fmt not in EXPORTS:
        raise HTTPException(status_code=404, detail=f"פורמט {fmt} אינו נתמך")
    rules = get_city_rules(city_code)
    try:
        dossier = await build_dossier(session, rules, opportunity_id, user.company_id)
    except NotEntitled as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    render, media_type = EXPORTS[fmt]
    try:
        payload = render(dossier)
    except RuntimeError as e:            # גופן חסר — שגיאת התקנה, לא של המשתמש
        raise HTTPException(status_code=503, detail=str(e)) from e

    stem = f'{dossier["identity"]["block"]}-{dossier["identity"]["parcel"]}'
    return Response(
        content=payload, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="shakdan-{stem}.{fmt}"'},
    )


@router.post("/{city_code}/{opportunity_id}/deliver")
async def deliver_opportunity(
    city_code: str,
    opportunity_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """מוסר הזדמנות לחברה ומנכה זכאות. קריאה חוזרת אינה מחייבת שוב.

    מועמד שתנאי הסף שלו לא נשאל — תיק הבניין נשלף **כאן**, בבקשה הזו,
    ואז המסירה מנוסה שוב. השליפה, ההערכה מחדש והמסירה הן עסקה אחת: תיק
    שנשלף ומסירה שנכשלה אחריו אינם יכולים להישאר במצבים שונים.
    """
    get_city_rules(city_code)
    try:
        # ‏SEL-01: הגרסאות והנימוק נקראים **אחרי** שהמועמד הוכן — אם התיק
        # נשלף בבקשה הזו, גרסת הנתונים חייבת לכלול אותו.
        async def prepare(s, oid):
            return await fetch_for_delivery(s, oid)

        row, charged = await deliver(session, opportunity_id, user.company_id, user.id,
                                     on_unready=prepare)
        if charged:
            p = await provenance(session, opportunity_id)
            row.rules_version, row.data_version, row.why_selected = (
                p["rules_version"], p["data_version"], p["why"])
            await session.flush()
    # שלוש סיבות שונות, שלושה קודים. ‏409 אומר ״המועמד הזה לא״; ‏503 אומר
    # ״נסה שוב״. להחזיר את שתיהן כ-409 פירושו שלקוח שהארכיון סירב לו יוותר
    # על מועמד תקין לחלוטין.
    except ArchiveUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except NoBuildingFile as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except NotDeliverable as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except NoCredits as e:
        raise HTTPException(status_code=402, detail=str(e)) from e
    await session.commit()
    return {"delivery_id": str(row.id), "opportunity_id": str(row.opportunity_id),
            "charged": charged, "delivered_at": row.delivered_at.isoformat()}


class RenewalDecision(BaseModel):
    """הכרעת הצוות על חשד לחידוש. בלי קישור אין ראיה — ולכן הוא חובה."""
    status: Literal["verified_renewed", "suspected", "none"]
    source: str = Field(min_length=2, max_length=300)
    evidence_url: str = Field(min_length=10, max_length=1000, pattern=r"^https?://")
    note: str | None = Field(default=None, max_length=1000)


@router.post("/{city_code}/{opportunity_id}/renewal")
async def set_renewal(
    city_code: str,
    opportunity_id: UUID,
    body: RenewalDecision,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_superuser),
) -> dict[str, Any]:
    """‏W5 · הצוות מאשר שהבניין חודש, או פוסל את החשד. נכתב כ-MANUALLY_VERIFIED
    וההערכה מחושבת מחדש מיד — כך שהסריקה הבאה כבר רואה את ההכרעה."""
    from app.cities.herzliya import renewal
    from app.cities.herzliya.assessments import refresh_one
    from app.models.opportunity import Opportunity

    rules = get_city_rules(city_code)
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None or opp.city_code != city_code:
        raise HTTPException(status_code=404, detail="המועמד לא נמצא")
    await renewal.record_team_decision(
        session, opp, status=body.status, source=body.source, evidence_url=body.evidence_url,
        note=body.note, checked_by=user.email)
    assessment = await refresh_one(session, rules, opportunity_id)
    await session.commit()
    return {"opportunity_id": str(opportunity_id),
            "renewal_status": assessment.get("renewal_status"),
            "renewal_reasons": assessment.get("renewal_reasons") or [],
            "assessment": assessment}


@router.get("/{city_code}")
async def list_candidates(
    city_code: str,
    min_area_sqm: float | None = Query(default=None),
    verification_level: str | None = Query(default=None),
    deliverable_only: bool = Query(default=False,
        description="רק מועמדים שההערכה שלהם ניתנת למסירה — לא מנותבים למתחמים ולא ללא קביעת קומות"),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_superuser),
) -> list[dict[str, Any]]:
    """Pre-filtered candidate opportunities for a given city — team screen only (#89)."""
    rules = get_city_rules(city_code)
    filters = {
        "exclude_delivered_ids": await delivered_ids(session, user.company_id),
        "min_area_sqm": min_area_sqm,
        "verification_level": verification_level,
        "deliverable_only": deliverable_only,
        "limit": limit,
    }
    return await rules.screen_candidates(session, filters)


@router.post("/{city_code}/unify")
async def check_unification(
    city_code: str,
    parcel_ids: list[str],
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """Check whether a set of adjacent parcels can be unified into one buildable lot."""
    rules = get_city_rules(city_code)
    result = await rules.check_plot_unification(session, parcel_ids)
    return {
        "is_unifiable": result.is_unifiable,
        "combined_area_sqm": result.combined_area_sqm,
        "parcel_ids": result.parcel_ids,
        "reason": result.reason,
    }
