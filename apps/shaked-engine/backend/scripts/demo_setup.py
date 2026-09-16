"""E8 · יוצר את חברת ההדגמה במסד שאין בו אחת.

    .venv/bin/python scripts/demo_setup.py            # מראה מה ייווצר, ולא יוצר
    .venv/bin/python scripts/demo_setup.py --apply    # יוצר; הסיסמה נשאלת ולא מודפסת

טל, בבדיקת הסביבה (#41): ‏`demo_reset.py` רק מאפס חברה קיימת, ואף סקריפט
לא יוצר אותה — ולכן במסד נקי אי אפשר להריץ את ההדגמה. זה הסקריפט החסר.

**מה נוצר:** חברה ש-slug שלה מתחיל ב-`demo-`, משתמש owner אחד בכתובת
`demo@shakdan.test`, ויתרה של `STARTING_CREDITS`. קיים כבר — לא נוגע בו.
הסיסמה נקראת מ-`getpass` (או מ-`DEMO_PASSWORD` בסביבה), ואינה נכתבת לשום
קובץ ולשום פלט. **מסרב** לעבוד על מסד שאינו על המחשב הזה.

במסד נקי אלוף יגאל אלון 2 אינה מוכנה (תיק הבניין שלה לא נשלף), ולכן הסריקה
באזור ההדגמה מוסרת את שלוש חלקות ההדגמה גם בלי מסירה מוקדמת (ראו #87).
"""
import argparse
import asyncio
import getpass
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_parcels as demo  # noqa: E402
from fastapi_users.password import PasswordHelper  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.package import Balance  # noqa: E402
from app.models.tenant import Company, User  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DEMO_EMAIL = "demo@shakdan.test"
DEMO_COMPANY_NAME = "חברת הדגמה"


async def main(apply: bool) -> int:
    host = urlparse(get_settings().database_url.replace("+asyncpg", "")).hostname
    if host not in LOCAL_HOSTS:
        print(f"מסרב: המסד על {host}, לא על המחשב הזה")
        return 2

    async with AsyncSessionLocal() as s:
        company = (await s.execute(select(Company).where(
            Company.slug.like(f"{demo.COMPANY_SLUG_PREFIX}%")))).scalars().first()
        user = (await s.execute(select(User).where(User.email == DEMO_EMAIL))).scalars().first()

        if company and user:
            print(f"חברת ההדגמה כבר קיימת ({company.name}), והמשתמש {DEMO_EMAIL} קיים — אין מה ליצור")
            print("לאיפוס אחרי חזרה: .venv/bin/python scripts/demo_reset.py --apply")
            return 0
        if user and not company:
            print(f"מסרב: {DEMO_EMAIL} קיים אבל שייך לחברה שאינה חברת הדגמה")
            return 2

        print(("ייווצר: " if not company else "קיים: ") + f"חברה {DEMO_COMPANY_NAME} (slug ‏{demo.COMPANY_SLUG_PREFIX}…), "
              f"יתרה {demo.STARTING_CREDITS}")
        print(f"ייווצר: משתמש owner {DEMO_EMAIL}")
        if not apply:
            print("\nלא נוצר דבר. להרצה: --apply")
            return 1

        password = os.environ.get("DEMO_PASSWORD") or getpass.getpass(f"סיסמה ל-{DEMO_EMAIL}: ")
        if len(password) < 8:
            print("מסרב: סיסמה קצרה מ-8 תווים. המנהרה חושפת את המסך לכל מי שיש לו את הכתובת.")
            return 2

        if company is None:
            company = Company(name=DEMO_COMPANY_NAME, slug=f"{demo.COMPANY_SLUG_PREFIX}{uuid.uuid4().hex[:8]}")
            s.add(company)
            await s.flush()
            s.add(Balance(company_id=company.id, credits_remaining=demo.STARTING_CREDITS))
        s.add(User(email=DEMO_EMAIL, hashed_password=PasswordHelper().hash(password),
                   is_active=True, is_superuser=False, is_verified=True,
                   full_name="משתמש הדגמה", role="owner", company_id=company.id))
        await s.commit()
        print("\nבוצע. להתחבר בכתובת שאינה localhost (שם נכנסים אוטומטית כמשתמש הפיתוח).")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="יצירת חברת ההדגמה במסד נקי")
    ap.add_argument("--apply", action="store_true", help="ליצור, ולא רק להציג")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
