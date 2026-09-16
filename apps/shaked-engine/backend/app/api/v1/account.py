"""חבילות ויתרה — ‏C13.

הטבלאות `packages` ו-`balances` היו קיימות מהיום הראשון ולא היה להן אף
נתיב, כך ש-C5 הניחה מסך יתרה שאין מי שמשרת אותו.

‏**ACC-03:** *״סריקה ריקה או הפקה שנכשלה אינן מפחיתות זכאות״*. אין כאן
נתיב שמנכה — הניכוי קורה **רק** ב-`deliver()`, ברגע שמגרש אמיתי נמסר.
זה לא במקרה: יתרה שאפשר להקטין מכמה מקומות מתחילה לסטות מהמסירות, ואז
אי אפשר לענות ללקוח על מה חויב.
"""
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.security import current_active_user
from app.models.package import Balance, CreditGrant, Delivery, Package
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
             "price_ils": float(p.price_ils)} for p in rows]


# ── רכישה מדומה, מאחורי דגל ──
#
# הרכישה המדומה הוסרה כי עם הרשמה פתוחה היא נתנה תיקים בחינם לכל נרשם.
# היא חוזרת **רק כש-`SIMULATED_PAYMENTS` דלוק** (טל, 16.09), כדי שאפשר יהיה
# להדגים את הזרימה המלאה עד שתחובר סליקה. כשהדגל כבוי הנתיב אינו קיים
# (404), והפיילוט ממשיך כמו קודם: תשלום בקישור, ואדמין מוסיף ב-`admin.py`.
# כל רכישה נרשמת ב-`credit_grants`, כך שיתרה מדומה אינה מתערבבת בשקט עם אמיתית.


class Purchase(BaseModel):
    method: Literal["card", "bit", "paypal"]


METHOD_LABEL = {"card": "כרטיס אשראי", "bit": "Bit", "paypal": "PayPal"}


@router.post("/packages/{package_id}/purchase")
async def purchase_package(
    package_id: UUID,
    body: Purchase,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
) -> dict[str, Any]:
    if not get_settings().simulated_payments:
        raise HTTPException(status_code=404, detail="Not Found")
    package = await session.get(Package, package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="החבילה אינה קיימת.")
    company_id, user_id = user.company_id, user.id
    balance = await _balance(session, company_id)
    balance.credits_remaining += package.credits
    session.add(CreditGrant(company_id=company_id, credits=package.credits, package_id=package.id,
                            note=f"תשלום מדומה · {METHOD_LABEL[body.method]}",
                            granted_by_user_id=user_id))
    await session.commit()
    return {"package": package.name, "credits_added": package.credits,
            "credits_remaining": balance.credits_remaining}
