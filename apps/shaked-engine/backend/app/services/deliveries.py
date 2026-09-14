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

‏**`on_unready` הוא הצד השני של אותה החלטה.** בלעדיו הלולאה פתוחה: הלקוח
לוחץ, מקבל 409, ושום דבר לא מושך את התיק. עם זה, המסירה היא הרגע שבו
הארכיון נשלף — חלקה אחת, לפי בקשה, בדיוק כפי שמרשם הסיכון מחייב
(`POC/layer_a/data/DATA_LAW.md`): *״סריקה לפי דרישה שצוברת כיסוי חלקי =
מטמון. סריקה יזומה של כל העיר = עותק של הארכיון העירוני.״*

ההזרקה היא callable ולא ייבוא של `archive_facts`, כדי שהשירות יישאר
עירוני-אגנוסטי — ובעיקר כדי שאפשר יהיה לבדוק את הלולאה בלי לגעת בארכיון.
"""
from collections.abc import Awaitable, Callable
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


def _assessment(opp: Opportunity) -> dict[str, Any]:
    return (opp.metadata_json or {}).get("assessment") or {}


def _is_deliverable(opp: Opportunity) -> bool:
    return bool(_assessment(opp).get("deliverable"))


def _open_gates(opp: Opportunity) -> list[str]:
    """רק שערים שאפשר לענות עליהם, ולכן באמת חוסמים.

    ‏`threshold_open` כולל גם שערים שאין להם מקור פתוח, ואלה **אינם**
    חוסמים מסירה. שמם בהודעת הסירוב היה מאשים את הצד הלא נכון: המשתמש
    קרא ״שער סף פתוח: residential_share״ ויצא לחפש נתון שלא קיים, בעוד
    שהסיבה האמיתית הייתה שלא נקבע מספר קומות.
    """
    from app.cities.herzliya import rights
    return [g for g in (_assessment(opp).get("threshold_open") or [])
            if g not in rights.UNOBTAINABLE]


def _why_not(opp: Opportunity) -> str:
    """הסיבה בפועל, ולא הרשימה שנמצאת ראשונה."""
    a = _assessment(opp)
    if not a:
        return "טרם חושבה הערכה למועמד"
    if open_gates := _open_gates(opp):
        return f"שערי סף שטרם נענו: {', '.join(open_gates)}"
    if not a.get("screenable"):
        status = a.get("status")
        if status == "urban_renewal_compound":
            return "המגרש נותב למסלול המתחמים, שכללי הזכויות שלו אחרים"
        if status == "ineligible":
            return "המועמד נפסל בתנאי הסף"
        if a.get("floors_low") is None:
            return "לא נקבע מספר קומות — רוחב הרחוב טרם נמדד"
    return "ההערכה אינה מסומנת כניתנת למסירה"


async def _credits(session, company_id: UUID) -> int:
    balance = (await session.execute(
        select(Balance.credits_remaining).where(Balance.company_id == company_id)
    )).scalar_one_or_none()
    return balance or 0


async def delivered_ids(session, company_id: UUID) -> set[UUID]:
    """מה שכבר נמסר לחברה. השאילתה שמסננת סריקה חוזרת."""
    return set((await session.execute(
        select(Delivery.opportunity_id).where(Delivery.company_id == company_id)
    )).scalars().all())


async def provenance(session, opportunity_id: UUID) -> dict[str, Any]:
    """גרסת הכללים, גרסת הנתונים והנימוק — ‏SEL-01.

    *״נשמרים גרסת הנתונים, גרסת הכללים והנימוק לכל בחירה״*. בלי אלה אין
    תשובה ללקוח ששואל בעוד חצי שנה למה דווקא המגרש הזה, ושתי הגרסאות הן
    מה שמבדיל בין ״המדיניות השתנתה״ לבין ״טעינו״.

    גרסת הנתונים אינה קבוע אלא **התצפית הטרייה ביותר שהכריעה בפועל** על
    המועמד הזה. שתי חלקות שנזרעו בהרצות שונות אינן על אותם נתונים, וקבוע
    אחד היה מטשטש את זה.
    """
    from app.cities.herzliya import rights
    from app.services.evidence_store import fields_for

    opp = await session.get(Opportunity, opportunity_id)
    fields = await fields_for(session, opportunity_id)
    stamps = [f["source"]["retrieved_at"] for f in fields.values()
              if (f.get("source") or {}).get("retrieved_at")]
    a = (opp.metadata_json or {}).get("assessment") or {} if opp else {}
    return {
        "rules_version": rights.RULES_VERSION,
        "data_version": max(stamps)[:10] if stamps else "",
        "why": {k: a.get(k) for k in
                ("status", "floors_low", "floors_high", "floors_certain",
                 "case_by_case", "cap_400_sqm", "cap_400_certainty", "threshold_open")
                if a.get(k) is not None},
    }


async def for_company(session, company_id: UUID) -> list[dict[str, Any]]:
    """מה שהחברה כבר קיבלה, עם הנימוק והגרסאות.

    החצי השני של SEL-02. ‏A13 סגר את הראשון — מגרש שנמסר אינו מוצע שוב —
    ואת זה לא: *״מגרש שכבר נמסר **מוצג במאגר החברה בלבד**״*. בלי הנתיב
    הזה לקוח משלם ואינו רואה את מה שקנה.
    """
    rows = (await session.execute(
        select(Delivery, Opportunity)
        .join(Opportunity, Opportunity.id == Delivery.opportunity_id)
        .where(Delivery.company_id == company_id)
        .order_by(Delivery.delivered_at.desc())
    )).all()
    return [{
        "delivery_id": str(d.id),
        "opportunity_id": str(d.opportunity_id),
        "address": o.address,
        "block": o.block,
        "parcel": o.parcel,
        "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
        "credits_charged": d.credits_charged,
        "rules_version": d.rules_version,
        "data_version": d.data_version,
        "why_selected": d.why_selected,
        "assessment": (o.metadata_json or {}).get("assessment"),
    } for d, o in rows]


async def deliver(session, opportunity_id: UUID, company_id: UUID,
                  user_id: UUID | None = None, *,
                  why: dict[str, Any] | None = None,
                  rules_version: str = "", data_version: str = "",
                  on_unready: Callable[[Any, UUID], Awaitable[bool]] | None = None,
                  ) -> tuple[Delivery, bool]:
    """מוסר הזדמנות לחברה. מחזיר (השורה, האם חויבה זכאות).

    אידמפוטנטי: קריאה שנייה על אותו צמד מחזירה את השורה הקיימת עם
    ``charged=False``, בלי לגעת ביתרה ובלי לשנות את `delivered_at` — מה
    שנמסר נמסר, וגם מי קיבל אותו ומתי אינו משתנה בדיעבד.

    ‏`on_unready(session, opportunity_id) -> bool` נקרא **פעם אחת** כשהמועמד
    אינו מוכן. אם הוא מחזיר True, ההערכה נקראת מחדש והמסירה מנוסה שוב.
    ניסיון אחד ולא לולאה: אם השליפה לא ענתה על השער, ניסיון נוסף ייפול
    באותו מקום ורק יפנה לארכיון שוב.
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

    if not _is_deliverable(opp) and on_unready is not None:
        # ‏**אין שליפה בשביל מי שאינו יכול לקבל את התוצאה.** הסדר היה:
        # שולפים את התיק, ורק אחר כך בודקים יתרה. כלומר חברה ביתרה 0 שלחצה
        # על מועמד לא מוכן גרמה לפנייה לארכיון העירוני — המשאב הרגיש ביותר
        # שיש לנו — בשביל תיק שלא יימסר לה. נמצא בהכנת ההדגמה (A21): שלב
        # ״מסירה רביעית → 402״ היה פונה לארכיון לפני ה-402.
        # מי שיש לו יתרה אינו מושפע: הסדר עבורו לא השתנה.
        if await _credits(session, company_id) < 1:
            raise NoCredits("לא נותרה זכאות לחברה")
        if await on_unready(session, opportunity_id):
            await session.refresh(opp)
    if not _is_deliverable(opp):
        raise NotDeliverable(
            f"המועמד אינו מוכן למסירה ולכן אינו צורך יתרה (ACC-05). {_why_not(opp)}"
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
