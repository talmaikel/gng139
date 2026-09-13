"""רישום המסירות — מה שהופך ״זכאות לשלוש הזדמנויות״ למשהו שאפשר לאכוף.

‏`Reservation` היה קיים לפני זה והוא דבר אחר: נעילה זמנית שמונעת מחברה
אחרת לראות מגרש בזמן שחברה אחת עובדת עליו. הוא אינו זוכר מה כבר נמסר,
ולכן שתי דרישות מרכזיות לא היו ניתנות לאכיפה — וגם היתרה לא, כי אי אפשר
לנכות זכאות בלי לדעת אם כבר נוכתה.

שלוש ההחלטות כאן, וכולן מלשון ה-PRD:

1. **הבעלות היא של החברה.** *״תוצאה שנמסרה למשתמש בחברה נחשבת תוצאה
   שנמסרה לחברה״*. משתמש אחר באותה חברה שסורק פוליגון חופף מקבל את אותה
   שורה, לא חיוב חדש (ACC-04).

2. **מסירה חוזרת אינה חינם — היא פשוט אותה מסירה.** ‏`deliver()` הוא
   אידמפוטנטי ומחזיר `charged=False`. אין ״ביטול״ ואין מחיקה: *״מגרש שכבר
   נמסר מוצג במאגר החברה בלבד ואינו צורך זכאות נוספת״*.

3. **מועמד שאינו מוכן אינו נמסר כלל.** ‏ACC-05: *״מועמד לא מוכן אינו צורך
   יתרה״*. ‏`assessment.deliverable` הוא בדיוק המבחן הזה, והוא False כל עוד
   שער סף של §70א לא נשאל — כלומר כל עוד לא נמשך תיק הבניין. זה מכוון:
   הארכיון נשלף לפי דרישת לקוח, ורגע המסירה הוא הרגע שבו זה קורה.
"""
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.opportunity import Opportunity
from app.models.package import Balance, Delivery


class NotDeliverable(Exception):
    """המועמד אינו מוכן למסירה. ‏ACC-05 — ואינו צורך יתרה."""


class NoCredits(Exception):
    """לחברה לא נותרה זכאות."""


async def delivered_ids(session, company_id: UUID) -> set[UUID]:
    """מה שכבר נמסר לחברה. השאילתה שמסננת סריקה חוזרת."""
    return set((await session.execute(
        select(Delivery.opportunity_id).where(Delivery.company_id == company_id)
    )).scalars().all())


async def deliver(session, opportunity_id: UUID, company_id: UUID,
                  user_id: UUID | None = None, *,
                  why: dict[str, Any] | None = None,
                  rules_version: str = "", data_version: str = "") -> tuple[Delivery, bool]:
    """מוסר הזדמנות לחברה. מחזיר (השורה, האם חויבה זכאות).

    אידמפוטנטי: קריאה שנייה על אותו צמד מחזירה את השורה הקיימת עם
    ``charged=False``, בלי לגעת ביתרה ובלי לשנות את `delivered_at` — מה
    שנמסר נמסר, וגם מי קיבל אותו ומתי אינו משתנה בדיעבד.
    """
    existing = (await session.execute(
        select(Delivery).where(Delivery.opportunity_id == opportunity_id,
                               Delivery.company_id == company_id)
    )).scalar_one_or_none()
    if existing is not None:
        return existing, False

    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise NotDeliverable(f"הזדמנות {opportunity_id} אינה קיימת")
    assessment = (opp.metadata_json or {}).get("assessment") or {}
    if not assessment.get("deliverable"):
        open_gates = assessment.get("threshold_open") or assessment.get("blocking") or []
        raise NotDeliverable(
            "המועמד אינו מוכן למסירה ולכן אינו צורך יתרה (ACC-05). "
            + (f"שערי סף פתוחים: {', '.join(open_gates)}" if open_gates
               else "ההערכה אינה מסומנת כניתנת למסירה")
        )

    balance = (await session.execute(
        select(Balance).where(Balance.company_id == company_id)
    )).scalar_one_or_none()
    if balance is None or balance.credits_remaining < 1:
        raise NoCredits("לא נותרה זכאות לחברה")

    row = Delivery(opportunity_id=opportunity_id, company_id=company_id,
                   delivered_to_user_id=user_id, credits_charged=1,
                   rules_version=rules_version, data_version=data_version,
                   why_selected=why)
    session.add(row)
    try:
        # ‏flush ולא commit: הטרנזקציה שייכת לקורא. האילוץ הייחודי הוא
        # ההגנה האמיתית מפני שתי סריקות במקביל — לא הבדיקה שלמעלה, שיכולה
        # להפסיד מרוץ בין שני משתמשים באותה חברה.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        again = (await session.execute(
            select(Delivery).where(Delivery.opportunity_id == opportunity_id,
                                   Delivery.company_id == company_id)
        )).scalar_one()
        return again, False

    balance.credits_remaining -= 1
    await session.flush()
    return row, True
