"""‏B14 · מסך = PDF = אקסל, על החלקות שבמסד. **קורא בלבד.**

‏`tests/test_surfaces.py` בודק תיק שנבנה מפיקסטורה. הסקריפט הזה בודק
את החלקות עצמן, אחרי הזריעה: **הסתירה של יום שני הופיעה רק על נתונים
אמיתיים**, כי רק שם יש שטח דירה מטביעת הרגל שאינו 70 מ״ר. בדיקה על
ערכי ברירת המחדל הייתה ירוקה, והיא אכן הייתה ירוקה.

לכל חלקה שיש לה תרחיש: בונה את התיק, מפיק PDF ואקסל, קורא אותם חזרה
ומשווה רווח, עלות ובסיס השבחה למה שהשרת מחזיר למסך.

    .venv/bin/python scripts/check_surfaces.py            # כל החלקות
    .venv/bin/python scripts/check_surfaces.py --limit 50

‏0 = שלושת המשטחים מסכימים · 1 = נמצאה סתירה · 2 = לא נבדקה אף חלקה.
**גם 2 הוא כישלון:** בדיקה שלא מצאה מה לבדוק אינה בדיקה שעברה.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.cities.herzliya import exports
from app.cities.herzliya.dossier import assemble
from app.cities.herzliya.rules import HerzliyaCityRules
from app.cities.herzliya.surfaces import compare
from app.core.database import AsyncSessionLocal
from app.models.opportunity import Opportunity


async def main(args) -> int:
    rules = HerzliyaCityRules()
    checked, skipped, broken = 0, 0, []
    started = time.monotonic()
    async with AsyncSessionLocal() as s:
        opps = (await s.execute(
            select(Opportunity)
            .where(Opportunity.city_code == "herzliya",
                   Opportunity.existing_units.isnot(None),
                   Opportunity.area_sqm.isnot(None))
            .order_by(Opportunity.block, Opportunity.parcel)
        )).scalars().all()
        for opp in opps:
            if args.limit and checked >= args.limit:
                break
            d = await assemble(s, rules, opp, None)
            if d["economics"].get("scenario") is None:
                skipped += 1
                continue
            checked += 1
            problems = compare(d, exports.excel(d), exports.pdf(d))
            if problems:
                # נשמר כטקסט: אחרי ה-rollback האובייקט כבר אינו קריא
                broken.append((f"{opp.address} · {opp.block}/{opp.parcel}", problems))
        await s.rollback()

    print(f"נבדקו {checked} חלקות עם תרחיש · {skipped} בלי תרחיש · "
          f"{time.monotonic() - started:.0f} שניות")
    for where, problems in broken[:20]:
        print(f"\n  !! {where}")
        for p in problems:
            print(f"     {p}")
    if len(broken) > 20:
        print(f"\n  ועוד {len(broken) - 20} חלקות עם סתירה")

    if checked == 0:
        print("\nלא נבדקה אף חלקה — אין תרחיש לאף הזדמנות במסד")
        return 2
    if broken:
        print(f"\n{len(broken)} מתוך {checked} חלקות מראות מספר אחר במסך, ב-PDF או באקסל")
        return 1
    print("המסך, ה-PDF והאקסל מסכימים בכל החלקות שנבדקו")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="מסך = PDF = אקסל — קריאה בלבד")
    ap.add_argument("--limit", type=int, default=0, help="עוצר אחרי N חלקות עם תרחיש")
    sys.exit(asyncio.run(main(ap.parse_args())))
