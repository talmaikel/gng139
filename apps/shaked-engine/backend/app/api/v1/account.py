"""חבילות ויתרה — ‏C13.

הטבלאות `packages` ו-`balances` היו קיימות מהיום הראשון ולא היה להן אף
נתיב, כך ש-C5 הניחה מסך יתרה שאין מי שמשרת אותו.

‏**ACC-03:** *״סריקה ריקה או הפקה שנכשלה אינן מפחיתות זכאות״*. אין כאן
נתיב שמנכה — הניכוי קורה **רק** ב-`deliver()`, ברגע שמגרש אמיתי נמסר.
זה לא במקרה: יתרה שאפשר להקטין מכמה מקומות מתחילה לסטות מהמסירות, ואז
אי אפשר לענות ללקוח על מה חויב.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.package import Balance, Delivery, Package
from app.models.tenant import User

router = APIRouter(prefix="/account", tags=["account"])


async def _balance(session: AsyncSession, company_id) -> Balance:
    """יתרת החברה, ונוצרת ריקה אם אין. אפס אינו שגיאה — הוא מצב."""
    row = (await session.execute(
        select(Balance).where(Balance.company_id == company_id))).scalar_one_or_none()
    if row is None:
        row = Balance(company_id=company_id, credits_remaining=0)
        session.add(row)
        await session.flush()
    return row


@router.get("/balance")
async def get_balance(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """היתרה, ולצידה כמה כבר נמסר — שני המספרים שמסך התוצאות מציג."""
    balance = await _balance(session, user.company_id)
    used = (await session.execute(
        select(Delivery).where(Delivery.company_id == user.company_id))).scalars().all()
    await session.commit()
    return {
        "credits_remaining": balance.credits_remaining,
        "delivered_count": len(used),
        # הזכאות שייכת לחברה ומשותפת לצוותה — לא למשתמש.
        "company_id": str(user.company_id),
        "updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
    }


@router.get("/packages")
async def list_packages(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Package).order_by(Package.credits))).scalars().all()
    return [{"id": str(p.id), "name": p.name, "credits": p.credits,
             "price_ils": p.price_ils} for p in rows]


@router.post("/packages/{package_id}/purchase")
async def purchase_package(
    package_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    """רכישה מדומה: מוסיפה זכאות לחברה. אין כאן סליקה.

    ‏**החבילה נרכשת לחברה ולא למשתמש** — ה-PRD מפורש: *״הזכאות לשלוש
    הזדמנויות שייכת לחברה ומשותפת לצוותה״*. וחבילה חדשה **אינה** פותחת
    מחדש מגרש שכבר נמסר (SEL-02) — רישום המסירות אינו נוגע ביתרה.
    """
    package = await session.get(Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="חבילה אינה קיימת")
    balance = await _balance(session, user.company_id)
    balance.credits_remaining += package.credits
    await session.commit()
    return {"package": package.name, "credits_added": package.credits,
            "credits_remaining": balance.credits_remaining}
