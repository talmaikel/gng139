"""מחירון הפיילוט — מסנכרן את טבלת `packages` לרשימה כאן.

    .venv/bin/python scripts/seed_packages.py            # מראה מה ישתנה, ולא משנה
    .venv/bin/python scripts/seed_packages.py --apply    # משנה

החבילה מזוהה לפי מספר ההזדמנויות: שינוי מחיר מעדכן את השורה הקיימת ולא
יוצר כפילות. חבילה שאינה ברשימה **אינה נמחקת** — ‏`credit_grants` מפנה אליה,
והיסטוריית ההענקות צריכה להמשיך לומר מה נקנה.
"""
import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.package import Package  # noqa: E402

# (הזדמנויות, שם, מחיר בש״ח)
PACKAGES: list[tuple[int, str, Decimal]] = [
    (3, "3 הזדמנויות", Decimal("19.90")),
    (12, "12 הזדמנויות", Decimal("49.90")),
    (30, "30 הזדמנויות", Decimal("99.90")),
]


async def main(apply: bool) -> int:
    async with AsyncSessionLocal() as s:
        existing = {p.credits: p for p in (await s.execute(select(Package))).scalars()}
        changes = 0
        for credits, name, price in PACKAGES:
            row = existing.get(credits)
            if row is None:
                print(f"+ {name} · {price} ₪")
                s.add(Package(name=name, credits=credits, price_ils=price))
                changes += 1
            elif row.name != name or Decimal(row.price_ils) != price:
                print(f"~ {row.name} · {row.price_ils} ₪  →  {name} · {price} ₪")
                row.name, row.price_ils = name, price
                changes += 1
            else:
                print(f"= {name} · {price} ₪")
        for credits, row in existing.items():
            if credits not in {c for c, _, _ in PACKAGES}:
                print(f"! {row.name} · {row.price_ils} ₪ — לא ברשימה, נשארת (לא נמחקת)")

        if not changes:
            print("אין מה לשנות.")
        elif apply:
            await s.commit()
            print(f"עודכנו {changes}.")
        else:
            print("לא שונה דבר. להרצה: --apply")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    sys.exit(asyncio.run(main(p.parse_args().apply)))
