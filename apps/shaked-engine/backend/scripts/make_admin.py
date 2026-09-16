"""הופך משתמש קיים לאדמין של המערכת — מי שמוסיף זכאות אחרי תשלום.

    .venv/bin/python scripts/make_admin.py dev@shaked.example.com           # מראה, ולא משנה
    .venv/bin/python scripts/make_admin.py dev@shaked.example.com --apply   # משנה
    .venv/bin/python scripts/make_admin.py dev@shaked.example.com --revoke --apply

אין לזה נתיב API בכוונה: מי שיכול למנות אדמין דרך האתר — כל פרצה באתר
הופכת אותו לאדמין. הסקריפט רץ רק ממי שיש לו גישה למסד.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.tenant import Company, User  # noqa: E402


async def main(email: str, apply: bool, revoke: bool) -> int:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(
            select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()
        if user is None:
            print(f"אין משתמש {email}. קודם להירשם באתר (/signup).")
            return 1
        company = await s.get(Company, user.company_id)
        target = not revoke
        print(f"{user.email} · {company.name if company else '?'} · אדמין: {user.is_superuser} → {target}")
        if user.is_superuser == target:
            print("אין מה לשנות.")
            return 0
        if not apply:
            print("לא שונה דבר. להרצה: --apply")
            return 0
        user.is_superuser = target
        await s.commit()
        print("עודכן. הכניסה הבאה של המשתמש תראה את /admin.")
        return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("email")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--revoke", action="store_true")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.email, a.apply, a.revoke)))
