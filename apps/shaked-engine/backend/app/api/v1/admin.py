"""הוספת זכאות ידנית — הפיילוט, בלי סליקה.

הלקוח לוחץ ״לרכישה צרו קשר״, משלם בקישור (Bit עסקי / PayPal), מקבל
חשבונית (Morning), ואדמין מוסיף לחברה שלו זכאות כאן. כל הוספה נרשמת
ב-`credit_grants` עם אסמכתה, כך שכל יתרה ניתנת לשחזור מול החשבוניות.

רק `is_superuser` — צוות שקדן. ‏owner של חברת לקוח **אינו** אדמין, ולקוח
שמנסה לקבל 403 ולא 404: הנתיב אינו סוד, ההרשאה היא ההגנה.
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.account import _balance
from app.core.database import get_async_session
from app.core.security import current_superuser
from app.models.package import Balance, CreditGrant, Package
from app.models.tenant import Company, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/companies")
async def find_companies(
    q: str = "",
    session: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
) -> list[dict[str, Any]]:
    """חיפוש לפי שם חברה או מייל של משתמש בה — הלקוח שילם ומזדהה במייל."""
    stmt = (
        select(Company, Balance.credits_remaining)
        .outerjoin(Balance, Balance.company_id == Company.id)
        .order_by(Company.created_at.desc())
        .limit(25)
    )
    term = q.strip()
    if term:
        like = f"%{term.lower()}%"
        members = select(User.company_id).where(func.lower(User.email).like(like))
        stmt = stmt.where(or_(func.lower(Company.name).like(like), Company.id.in_(members)))

    rows = (await session.execute(stmt)).all()
    ids = [c.id for c, _ in rows]
    emails: dict[UUID, list[str]] = {}
    if ids:
        for company_id, email in (await session.execute(
                select(User.company_id, User.email).where(User.company_id.in_(ids)))).all():
            emails.setdefault(company_id, []).append(email)

    return [{"id": str(c.id), "name": c.name, "emails": emails.get(c.id, []),
             "credits_remaining": credits or 0,
             "created_at": c.created_at.isoformat() if c.created_at else None}
            for c, credits in rows]


class GrantRequest(BaseModel):
    # ‏package_id או credits — חבילה קובעת את הכמות, ומספר חופשי הוא לתיקון.
    package_id: UUID | None = None
    credits: int | None = Field(default=None, ge=1, le=1000)
    note: str = Field(min_length=2, max_length=500)


@router.post("/companies/{company_id}/credits")
async def grant_credits(
    company_id: UUID,
    body: GrantRequest,
    session: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
) -> dict[str, Any]:
    """מוסיף זכאות לחברה ורושם מי, כמה, ועל סמך איזו אסמכתה.

    ‏**הזכאות היא של החברה** (ה-PRD: *״שייכת לחברה ומשותפת לצוותה״*),
    ואינה פותחת מחדש מגרש שכבר נמסר — ‏SEL-02 נשען על `deliveries`, לא על היתרה.
    """
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="חברה אינה קיימת.")

    package = None
    if body.package_id is not None:
        package = await session.get(Package, body.package_id)
        if package is None:
            raise HTTPException(status_code=404, detail="חבילה אינה קיימת.")
    credits = package.credits if package else body.credits
    if not credits:
        raise HTTPException(status_code=422, detail="יש לבחור חבילה או מספר הזדמנויות.")

    balance = await _balance(session, company.id)
    balance.credits_remaining += credits
    session.add(CreditGrant(company_id=company.id, credits=credits,
                            package_id=package.id if package else None,
                            note=body.note.strip(), granted_by_user_id=admin.id))
    await session.commit()
    return {"company": company.name, "credits_added": credits,
            "credits_remaining": balance.credits_remaining}


@router.get("/companies/{company_id}/credits")
async def grant_history(
    company_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    admin: User = Depends(current_superuser),
) -> list[dict[str, Any]]:
    """כל ההוספות לחברה, מהחדשה — מול החשבוניות."""
    rows = (await session.execute(
        select(CreditGrant, User.email)
        .outerjoin(User, User.id == CreditGrant.granted_by_user_id)
        .where(CreditGrant.company_id == company_id)
        .order_by(CreditGrant.created_at.desc()))).all()
    return [{"credits": g.credits, "note": g.note, "granted_by": email,
             "created_at": g.created_at.isoformat() if g.created_at else None}
            for g, email in rows]
