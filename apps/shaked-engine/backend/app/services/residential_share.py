"""‏W10 · #115 · יחס המגורים של §70א, מטבלת השטחים בגרמושקה.

השותפים שאלו איך יודעים שלפחות 70% מהשטח הבנוי משמש למגורים. התשובה
בטבלת השטחים שבהיתר, ואין לה מקור פתוח. חילוץ אוטומטי של שטחי השימושים
עדיין אין; עד אז אדם קורא את הטבלה ומזין שני מספרים, והיחס נכתב כראיה
‏`MANUALLY_VERIFIED` עם הקישור לגרמושקה — ומכריע את השער.

שלוש החלטות:

1. **שטחי שירות למגורים נספרים כמגורים** — לשון §70א: *״ובכלל זה לשטחי
   שירות למגורים״*. המסך אומר זאת ליד השדה, כי שם טועים.

2. **הזנה חוזרת מחליפה את ההזנה הידנית הקודמת**, ולא נערמת עליה. שתי
   הזנות שונות היו הופכות לסתירה, והשער היה חוזר ל״לא ידוע״ בשקט. ראיה
   מסוג אחר, אם תהיה, נשארת — וסתירה מולה היא סתירה אמיתית.

3. **מי הזין — לא נשמר.** אין לכך עמודה ב-`field_evidence`, והראיה שייכת
   להזדמנות ולא לחברה: כל חברה שקיבלה את התיק רואה את המיקום ואת השיטה.
   אימייל של משתמש בחברה אחת היה נחשף בתיק של חברה אחרת.

ובלי שינוי מהיום: הזנה מאבדת את כוח ההכרעה אחרי `source_max_age_days`,
כמו כל ראיה, והשער חוזר ל״לא ידוע״.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.cities.herzliya.assessments import refresh_one
from app.cities.herzliya.rules import HerzliyaCityRules
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity
from app.services.evidence_store import deciding, fields_for

FIELD = "residential_share"
METHOD = "הוזן ידנית מטבלת השטחים בגרמושקה; שטחי שירות למגורים נספרים כמגורים (§70א)"


def location_for(residential_sqm: float, total_sqm: float,
                 page: str | None = None, note: str | None = None) -> str:
    """איפה בהיתר, ומה נקרא שם — כדי שאפשר יהיה לבדוק אותנו מול הדף."""
    parts = ["טבלת השטחים בהיתר"]
    if page:
        parts.append(f"עמ׳ {page}")
    parts.append(f"{residential_sqm:,.0f} מתוך {total_sqm:,.0f} מ״ר מגורים")
    if note:
        parts.append(f"הערה: {note}")
    return " · ".join(parts)


async def record(session, opportunity_id: UUID, *, residential_sqm: float, total_sqm: float,
                 source_url: str, page: str | None = None, note: str | None = None,
                 now: datetime | None = None) -> None:
    """כותב את היחס כראיה מאומתת ומרענן את ההערכה השמורה. אינו עושה commit."""
    if not 0 < residential_sqm <= total_sqm:
        raise ValueError("שטח המגורים חייב להיות חיובי ולא לעלות על השטח הבנוי הכולל")
    page = (page or "").strip() or None
    note = (note or "").strip() or None

    await session.execute(delete(FieldEvidence).where(
        FieldEvidence.opportunity_id == opportunity_id,
        FieldEvidence.field == FIELD,
        FieldEvidence.building_id.is_(None),
        FieldEvidence.certainty == Certainty.MANUALLY_VERIFIED,
    ))
    session.add(FieldEvidence(
        opportunity_id=opportunity_id, field=FIELD,
        value=round(residential_sqm / total_sqm, 4),
        certainty=Certainty.MANUALLY_VERIFIED,
        source_url=source_url.strip(),
        retrieved_at=now or datetime.now(timezone.utc),
        location=location_for(residential_sqm, total_sqm, page, note),
        method=METHOD,
    ))
    await session.flush()
    await refresh_one(session, HerzliyaCityRules(), opportunity_id)


async def state(session, opportunity: Opportunity) -> dict[str, Any]:
    """הערך שהשער רואה, ההזנה הידנית שמאחוריו, והשער עצמו כפי שיופיע בתיק."""
    fields = await fields_for(session, opportunity.id)
    field = fields.get(FIELD) or {}
    a = await HerzliyaCityRules().assess(session, opportunity.id)
    gate = next(c for c in a["checks"] if c["id"] == FIELD)

    row = (await session.execute(
        select(FieldEvidence).where(
            FieldEvidence.opportunity_id == opportunity.id,
            FieldEvidence.field == FIELD,
            FieldEvidence.building_id.is_(None),
            FieldEvidence.certainty == Certainty.MANUALLY_VERIFIED,
        ).order_by(FieldEvidence.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    stored = (opportunity.metadata_json or {}).get("assessment") or {}
    return {
        "opportunity_id": str(opportunity.id),
        "address": opportunity.address,
        # מה שהשער מכריע לפיו בפועל — None כשאין, כשהוא התיישן או כשיש סתירה
        "residential_share": deciding(fields).get(FIELD),
        "certainty": field.get("certainty"),
        "stale": FIELD in a["stale_fields"],
        "entry": None if row is None else {
            "residential_share": row.value,
            "source_url": row.source_url,
            "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
            "location": row.location,
            "method": row.method,
        },
        "gate": gate,
        "assessment": {"status": stored.get("status"), "deliverable": stored.get("deliverable")},
    }
