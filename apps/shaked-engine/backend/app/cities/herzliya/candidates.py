"""Pre-filtered candidate screening for Herzliya opportunities."""

import json
from typing import Any

from sqlalchemy import Float, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cities.herzliya.xplan_schema import QUEUE_ELIGIBLE_CATEGORIES
from app.models.opportunity import Opportunity
from app.cities.herzliya.boundary import search_polygon_wkt


# השדות שהיזם רשאי למיין לפיהם, וכיצד כל אחד נקרא מהשורה.
# ‏PRD 4.2: מיון מפורש לפי סדר שהיזם מגדיר — לא ניקוד משוקלל סמוי.
SORTABLE: dict[str, tuple[Any, str]] = {
    "parcel_area": (Opportunity.area_sqm, "שטח המגרש"),
    "units": (Opportunity.existing_units, "מספר הדירות הקיים"),
    "floors": (Opportunity.metadata_json["assessment"]["floors_low"].astext.cast(Float),
               "מספר הקומות המותר"),
    "cap_400": (Opportunity.metadata_json["assessment"]["cap_400_sqm"].astext.cast(Float),
                'תקרת 400% במ"ר'),
}


# תנאי חובה — נפרדים מהעדפות **בכוונה**, וזה ההבדל שה-PRD עומד עליו
# ב-SEL-01: *״המערכת מחילה כללים, תנאי חובה וסדר העדיפויות״*. תנאי חובה
# מוציא מועמד מהרשימה; העדפה רק מזיזה אותו בה. לערבב ביניהם פירושו או
# להסתיר מועמדים שהיזם היה רוצה לראות, או להציג מועמדים שאינם רלוונטיים
# ולקרוא לזה ״מדורג נמוך״.
MANDATORY: dict[str, tuple[Any, str]] = {
    "min_area_sqm": (Opportunity.area_sqm, "שטח מגרש מזערי"),
    "min_units": (Opportunity.existing_units, "מספר דירות קיים מזערי"),
    "min_floors": (Opportunity.metadata_json["assessment"]["floors_low"].astext.cast(Float),
                   "מספר קומות מותר מזערי"),
    "min_cap_400_sqm": (Opportunity.metadata_json["assessment"]["cap_400_sqm"].astext.cast(Float),
                        'תקרת 400% מזערית במ"ר'),
}


def _mandatory(stmt, filters: dict[str, Any]):
    """מחיל את תנאי החובה. ערך חסר **אינו** עובר תנאי מזערי.

    ‏`NULL >= 5` הוא NULL ולא TRUE, ולכן שורה בלי קביעת קומות נופלת מאליה
    כשמבקשים מינימום קומות — וזו התנהגות נכונה: ״לא ידוע״ אינו ״עומד
    בתנאי״. הכתיבה המפורשת כאן היא כדי שזה לא ייראה כמו מקרה.
    """
    for key, (col, _) in MANDATORY.items():
        if (value := filters.get(key)) is not None:
            stmt = stmt.where(col >= value)
    # ‏W6 · ״מקסימום דירות קיימות״ (בועז, 16.09): פחות בעלים להחתים. ‏NULL אינו עומד.
    if (value := filters.get("max_units")) is not None:
        stmt = stmt.where(Opportunity.existing_units <= value)

    # קביעת קומות ודאית: כל רוחב הרחוב בטווח הסובלנות נותן אותה תשובה.
    # יזם שמתכנן לפי המספר צריך לדעת שהוא אינו זז.
    if filters.get("certain_floors_only"):
        stmt = stmt.where(
            Opportunity.metadata_json["assessment"]["floors_certain"].astext == "true")
    return stmt


def _ordered(stmt, preferences: list[dict[str, Any]]):
    """מיון לקסיקוגרפי לפי סדר ההעדפות, ואז מזהה יציב לשבירת שוויון מלא.

    שדה מיון חסר ממוקם **אחרי** ערכים ידועים (PRD 4.2), אחרת חוסר מידע
    היה נראה כמו יתרון.
    """
    order = []
    for pref in preferences:
        col, _ = SORTABLE.get(pref.get("field"), (None, None))
        if col is None:
            continue
        order.append(col.desc().nullslast() if pref.get("direction", "desc") == "desc"
                     else col.asc().nullslast())
    return stmt.order_by(*order, Opportunity.id)


def _why_selected(rows: list[dict[str, Any]], preferences: list[dict[str, Any]]) -> None:
    """מוסיף לכל שורה את ההעדפה שהכריעה אותה מול הבאה אחריה.

    זה מה ש-SEL-01 דורש — נימוק לכל בחירה — ולא הסבר כללי על המיון.
    """
    if not preferences:
        for r in rows:
            r["why_selected"] = "לא הוגדרו העדפות; הסדר לפי מזהה יציב"
        return
    for i, row in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        decided = None
        for pref in preferences:
            field = pref.get("field")
            if field not in SORTABLE:
                continue
            mine, theirs = _value(row, field), _value(nxt, field) if nxt else None
            if nxt is None or mine != theirs:
                decided = (field, mine, theirs)
                break
        if decided is None:
            row["why_selected"] = "זהה לבא אחריו בכל ההעדפות; הוכרע במזהה יציב"
            continue
        field, mine, theirs = decided
        label = SORTABLE[field][1]
        shown = "—" if mine is None else f"{mine:,.0f}" if isinstance(mine, (int, float)) else mine
        row["why_selected"] = (f"{label}: {shown}" if theirs is None else
                               f"{label}: {shown} מול {theirs:,.0f} בבא אחריו")


def _value(row: dict[str, Any] | None, field: str):
    if row is None:
        return None
    if field == "parcel_area":
        return row.get("area_sqm")
    if field == "units":
        return row.get("existing_units")
    a = row.get("assessment") or {}
    return a.get("floors_low") if field == "floors" else a.get("cap_400_sqm")


async def screen_herzliya_candidates(session: AsyncSession, filters: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return pre-filtered candidate addresses for Herzliya, restricted to
    opportunities whose screening category is queue-eligible
    (`primary_candidate` / `needs_verification`) unless the caller overrides it.

    The category is set by the Layer-A seeder from the policy map and the
    archive, **not** by XPlan — an earlier version of this docstring said
    XPlan and there is no XPlan screening step here. `xplan_code` is NULL
    on every seeded row for the same reason, and is therefore omitted from
    the response rather than returned as a null the client has to guess at.
    """
    geometry_geojson = func.ST_AsGeoJSON(Opportunity.geom)
    centroid = func.ST_Centroid(Opportunity.geom)
    centroid_lat = func.ST_Y(centroid)
    centroid_lng = func.ST_X(centroid)

    stmt = select(Opportunity, geometry_geojson, centroid_lat, centroid_lng).where(
        Opportunity.city_code == "herzliya"
    )

    # אזור חיפוש מצויר. הסינון נעשה ב-PostGIS ולא ב-Python: 699 פוליגונים
    # הם מעט, אבל המדד המרחבי קיים והשאילתה אמורה להישאר זולה גם כשיהיו יותר.
    if (poly := filters.get("polygon")) is not None:
        stmt = stmt.where(
            func.ST_Intersects(Opportunity.geom, func.ST_GeomFromText(search_polygon_wkt(poly), 4326))
        )

    categories = filters.get("categories") or list(QUEUE_ELIGIBLE_CATEGORIES)
    stmt = stmt.where(Opportunity.metadata_json["category"].astext.in_(categories))

    stmt = _mandatory(stmt, filters)

    # מועמד שנפסל בשערים אינו מוצג כלל. מי שאין לו קביעת קומות אינו
    # "מדורג נמוך" אלא אינו בר-מסירה — זו מוכנות, לא העדפה.
    #
    # ‏`IS DISTINCT FROM` ולא `!=`: בשורה שאין בה `assessment` האופרנד הוא
    # NULL, ו-`NULL != 'x'` הוא NULL — שאינו TRUE, ולכן השורה **נופלת**.
    # זריעה חוזרת דורסת את `metadata_json` בלי ההערכה, וכל 699 המועמדים
    # היו נעלמים מה-API בלי שגיאה. מי שטרם הוערך צריך להופיע, לא להיעלם.
    stmt = stmt.where(
        Opportunity.metadata_json["assessment"]["status"].astext.is_distinct_from("ineligible")
    )
    # ‏`screenable` ולא `deliverable`: המסך מציג מי נשאר במסלול, ולא מי
    # שתנאי הסף שלו כבר נענה במלואו. השניים התבלבלו כאן, והתוצאה הייתה
    # שכל העיר הוצגה כמוכנה למסירה.
    # ‏SEL-02: *״אותו מגרש אינו נספר שוב בעקבות פוליגון חופף, שינוי כתובת,
    # שינוי משתמש בחברה או חבילה חדשה״*. הסינון הוא ברמת החברה, כי הזכאות
    # היא של החברה — שני משתמשים באותה חברה הסורקים פוליגונים חופפים אינם
    # מקבלים את המגרש פעמיים (ACC-04).
    if delivered := filters.get("exclude_delivered_ids"):
        stmt = stmt.where(Opportunity.id.notin_(list(delivered)))

    if filters.get("deliverable_only"):
        stmt = stmt.where(Opportunity.metadata_json["assessment"]["screenable"].astext == "true")

    if verification_level := filters.get("verification_level"):
        stmt = stmt.where(Opportunity.verification_level == verification_level)

    stmt = _ordered(stmt, filters.get("preferences") or [])
    stmt = stmt.limit(int(filters.get("limit", 100)))

    result = await session.execute(stmt)
    rows = [
        {
            "id": str(opp.id),
            "address": opp.address,
            "block": opp.block,
            "parcel": opp.parcel,
            "area_sqm": opp.area_sqm,
            "existing_units": opp.existing_units,
            "verification_level": opp.verification_level,
            "category": opp.metadata_json.get("category"),
            "assessment": opp.metadata_json.get("assessment"),
            # ‏W5 · מסך הצוות מציג את החשד ואת נימוקיו, לאישור או לפסילה
            "renewal_status": (opp.metadata_json.get("assessment") or {}).get("renewal_status"),
            "renewal_reasons": (opp.metadata_json.get("assessment") or {}).get("renewal_reasons") or [],
            "geometry": json.loads(geojson) if geojson else None,
            "centroid": {"lat": lat, "lng": lng} if lat is not None and lng is not None else None,
        }
        for opp, geojson, lat, lng in result.all()
    ]
    _why_selected(rows, filters.get("preferences") or [])
    return rows
