"""קריאת ראיות מבסיס הנתונים, והפיכתן לשדות שאפשר להכריע לפיהם.

‏`app/evidence.py` מחזיק את הכללים — `resolve_evidence()` שמזהה סתירה
במקום לדרוס, ו-`usable()` שמחליטה אם תצפית רשאית להכריע בדיקה. שתיהן
עובדות על dict. **הזורע כותב שורות, ועד עכשיו איש לא קרא אותן בחזרה**,
כך שהראיות נצברו בלי שאיש יתייעץ בהן והגיל מעולם לא נבדק בפועל.

הקובץ הזה הוא החוליה החסרה: שורות → תצפיות → שדה מוכרע → `usable()`.

שתי התנהגויות שנובעות מזה וחשוב להכיר:

1. **סתירה אינה נפתרת לפי "האחרון שנשלף".** שני מקורות שחלוקים על אותו
   שדה מייצרים `conflict` שמחזיק את שתי התצפיות, והשדה אינו מכריע דבר.

2. **גיל חוסם.** מקור שנשלף לפני יותר מ-`SOURCE_MAX_AGE_DAYS` מפסיק
   להכריע — בשקט, בלי שגיאה. זו התנהגות מכוונת, והיא תיראה בדיוק כמו
   באג ביום שבו הנתונים יתיישנו. `stale_fields()` קיימת כדי שאפשר יהיה
   לראות את זה מראש ולא לגלות מול לקוח.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.evidence import evidence, resolve_evidence, usable
from app.models.evidence import FieldEvidence


def _as_observation(row: FieldEvidence) -> dict[str, Any]:
    """שורה → תצפית בצורה ש-`usable()` יודעת לקרוא."""
    source = None
    if row.source_url:
        source = {"url": row.source_url,
                  "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None}
        if row.feature_url:
            source["feature_url"] = row.feature_url
    return evidence(row.value, source=source, certainty=row.certainty,
                    location=row.location, method=row.method)


async def fields_for(session, opportunity_id: UUID, *, building_id: UUID | None = None
                     ) -> dict[str, dict[str, Any]]:
    """כל השדות של הזדמנות אחת, מוכרעים. מפתח → שדה."""
    stmt = select(FieldEvidence).where(FieldEvidence.opportunity_id == opportunity_id)
    stmt = stmt.where(FieldEvidence.building_id == building_id) if building_id else \
        stmt.where(FieldEvidence.building_id.is_(None))
    rows = (await session.execute(stmt)).scalars().all()

    by_field: dict[str, list] = {}
    for r in rows:
        by_field.setdefault(r.field, []).append(_as_observation(r))
    return {name: resolve_evidence(obs) for name, obs in by_field.items()}


def deciding(fields: dict[str, dict], *, now: datetime | None = None) -> dict[str, Any]:
    """רק השדות שרשאים להכריע, כערכים. השאר פשוט אינם כאן."""
    return {k: f["value"] for k, f in fields.items()
            if usable(f, get_settings().source_max_age_days, now)}


def stale_fields(fields: dict[str, dict], *, now: datetime | None = None) -> list[str]:
    """שדות שהיו מכריעים אלמלא גילם — האזהרה לפני שהכול נשבר בשקט."""
    now = now or datetime.now(timezone.utc)
    out = []
    for name, f in fields.items():
        if usable(f, get_settings().source_max_age_days, now):
            continue
        # גיל בלבד: כל השאר תקין, ורק הזמן פוסל
        if usable(f, 10**6, now):
            out.append(name)
    return out
