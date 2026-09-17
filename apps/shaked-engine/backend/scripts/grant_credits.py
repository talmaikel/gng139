"""מוסיף זכאות (הזדמנויות) לחברה של משתמש נתון — מראה קודם, ומשנה רק עם --apply.

    .venv/Scripts/python scripts/grant_credits.py admin@gng139.online 999 --note "..."
    .venv/Scripts/python scripts/grant_credits.py admin@gng139.online 999 --note "..." --apply

מדמה בדיוק את POST /api/v1/admin/companies/{id}/credits: היתרה שייכת
לחברה, וכל הוספה נרשמת ב-credit_grants עם אסמכתה כדי שתישאר ניתנת
לשחזור מול חשבוניות (ראו app/api/v1/admin.py).
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.api.v1.account import _balance  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.package import CreditGrant  # noqa: E402
from app.models.tenant import Company, User  # noqa: E402


async def main(email: str, credits: int, note: str, apply: bool) -> int:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()
        if user is None:
            print(f"אין משתמש {email}.")
            return 1
        company = await s.get(Company, user.company_id)
        if company is None:
            print(f"למשתמש {email} אין חברה משויכת.")
            return 1

        balance = await _balance(s, company.id)
        print(f"{user.email} · חברה: {company.name} · יתרה נוכחית: {balance.credits_remaining} "
              f"→ {balance.credits_remaining + credits}")

        if not apply:
            print("לא שונה דבר. להרצה בפועל: --apply")
            await s.rollback()
            return 0

        balance.credits_remaining += credits
        s.add(CreditGrant(company_id=company.id, credits=credits, note=note,
                           granted_by_user_id=user.id))
        await s.commit()
        print(f"עודכן. יתרה חדשה: {balance.credits_remaining}")
        return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("email")
    p.add_argument("credits", type=int)
    p.add_argument("--note", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.email, a.credits, a.note, a.apply)))
