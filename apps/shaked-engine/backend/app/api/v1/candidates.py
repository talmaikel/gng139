from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities import get_city_rules as _get_city_rules
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.tenant import User
from app.cities.herzliya.archive_facts import (ArchiveUnavailable, NoBuildingFile,
                                               fetch_for_delivery)
from app.cities.herzliya import exports
from app.cities.herzliya.dossier import NotEntitled, build as build_dossier
from app.services.deliveries import (NoCredits, NotDeliverable, _credits, deliver,
                                     delivered_ids, for_company, provenance)

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


@router.post("/{city_code}/search")
async def search_candidates(
    city_code: str,
    body: SearchArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """מועמדים בתוך אזור מצויר. פוליגון שאינו תקין או חורג מהעיר נדחה ב-422."""
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
# שליפה מהארכיון היא 10–20 שניות, והארכיון מוגבל בקצב. יותר משתיים
# בבקשה אחת עוברות את זמן ההמתנה של הדפדפן; השאר מושלמות בקריאה נוספת.
MAX_FETCHES_PER_SCAN = 2


class ScanArea(BaseModel):
    """אותו אזור ואותם תנאים כמו `SearchArea`, בלי `limit`: הסריקה קובעת
    כמה, לפי היתרה."""
    polygon: dict[str, Any]
    min_area_sqm: float | None = Field(default=None, ge=0)
    min_units: int | None = Field(default=None, ge=0)
    min_floors: float | None = Field(default=None, ge=0)
    min_cap_400_sqm: float | None = Field(default=None, ge=0)
    certain_floors_only: bool = False
    preferences: list[Preference] = Field(default_factory=list, max_length=3)


def _ready(row: dict[str, Any]) -> bool:
    return bool((row.get("assessment") or {}).get("deliverable"))


async def _scan_queue(session, rules, body: ScanArea, company_id) -> list[dict[str, Any]]:
    """המועמדים שהסריקה תמסור, בסדר שבו תמסור אותם.

    **מוכנים קודם** (בועז, 15.09): תיק שכבר נשלף נמסר מיד ובוודאות. אחריהם
    מי שבמסלול המגרשי אבל דורש שליפה מהארכיון. בתוך כל קבוצה — לפי
    ההעדפות של הלקוח, כי `screen_candidates` כבר מיין כך והמיון יציב.
    """
    filters = body.model_dump() | {
        "limit": 500,
        "exclude_delivered_ids": await delivered_ids(session, company_id),
    }
    try:
        rows = await rules.screen_candidates(session, filters)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    in_track = [r for r in rows
                if _ready(r) or (r.get("assessment") or {}).get("screenable")]
    return [r for r in in_track if _ready(r)] + [r for r in in_track if not _ready(r)]


@router.post("/{city_code}/scan/preview")
async def scan_preview(
    city_code: str,
    body: ScanArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """כמה יימסרו, לפני החיוב. **מספרים בלבד** — בלי כתובת, מזהה או גאומטריה."""
    rules = get_city_rules(city_code)
    queue = await _scan_queue(session, rules, body, user.company_id)
    credits = await _credits(session, user.company_id)
    offer = min(SCAN_SIZE, credits, len(queue))
    ready = sum(1 for r in queue[:offer] if _ready(r))
    return {"found": len(queue), "offer": offer, "ready": ready,
            "needs_fetch": offer - ready, "credits_remaining": credits}


@router.post("/{city_code}/scan/deliver")
async def scan_deliver(
    city_code: str,
    body: ScanArea,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """מוסר עד שלושה מגרשים מהאזור, לפי סדר `_scan_queue`.

    מגרש שאין לו תיק בניין או שהשליפה לא ענתה על השער — מדלגים לבא אחריו,
    ואינו מחויב (ACC-05). ארכיון שסירב — עוצרים ומחזירים `retryable`:
    קריאה חוזרת משלימה, כי מה שכבר נמסר אינו מוצע שוב. כל מסירה נשמרת
    מיד, כך שבקשה שנקטעה באמצע אינה מאבדת את מה שכבר נמסר.
    """
    rules = get_city_rules(city_code)
    # ‏rollback על מגרש שדולג מפקיע את כל האובייקטים בסשן, כולל המשתמש;
    # קריאה של `user.company_id` אחריו הייתה פונה למסד מחוץ להקשר האסינכרוני.
    company_id, user_id = user.company_id, user.id
    credits = await _credits(session, company_id)
    if credits < 1:
        raise HTTPException(status_code=402, detail="לא נותרה זכאות לחברה. יש לרכוש חבילה כדי להמשיך.")
    queue = await _scan_queue(session, rules, body, company_id)
    target = min(SCAN_SIZE, credits)

    async def prepare(s, oid):
        return await fetch_for_delivery(s, oid)

    delivered: list[str] = []
    skipped, fetches, retryable, message = 0, 0, False, None
    for candidate in queue:
        if len(delivered) >= target:
            break
        if not _ready(candidate):
            if fetches >= MAX_FETCHES_PER_SCAN:
                retryable = True
                message = "חלק מהתיקים עוד נשלפים מהארכיון. לחיצה נוספת תשלים אותם."
                break
            fetches += 1
        oid = UUID(candidate["id"])
        try:
            row, charged = await deliver(session, oid, company_id, user_id,
                                         on_unready=prepare)
            if charged:
                p = await provenance(session, oid)
                row.rules_version, row.data_version, row.why_selected = (
                    p["rules_version"], p["data_version"], p["why"])
                await session.flush()
            await session.commit()
            if charged:
                delivered.append(str(oid))
        except (NoBuildingFile, NotDeliverable):
            await session.rollback()
            skipped += 1
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
        "requested": target,
        "skipped": skipped,
        "retryable": retryable,
        "message": message,
        "credits_remaining": await _credits(session, company_id),
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


@router.get("/{city_code}")
async def list_candidates(
    city_code: str,
    min_area_sqm: float | None = Query(default=None),
    verification_level: str | None = Query(default=None),
    deliverable_only: bool = Query(default=False,
        description="רק מועמדים שההערכה שלהם ניתנת למסירה — לא מנותבים למתחמים ולא ללא קביעת קומות"),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    """Pre-filtered candidate opportunities for a given city, applying the city's own strategy."""
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
