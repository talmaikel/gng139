"""‏A21 · מחזיר את חברת ההדגמה לנקודת ההתחלה, אחרי חזרה.

    .venv/bin/python scripts/demo_reset.py            # מראה מה ישתנה, ולא משנה
    .venv/bin/python scripts/demo_reset.py --apply    # משנה

החזרה ביום רביעי בבוקר (A7, ‏C11) מוסרת את שלוש חלקות ההדגמה ומורידה את
היתרה ל-0. בלי איפוס, ״מסור לי״ בהדגמה עצמה מחזיר ״פתח תיק״ במקום מסירה,
והמסירה הרביעית אינה מחזירה 402.

**מה נמחק:** רק מסירות של ארבע חלקות ההדגמה, ורק לחברת ההדגמה. ארבע
המסירות הישנות מ-13.09 נשארות — זו הכרעה נפרדת (A23). וגם התמהיל שחושב
לחלקות ההדגמה בחזרה (B15), כדי שבהדגמה התיק ייפתח עם ״עוד לא חושב״.

**מה לא נמחק:** מסירה של חלקה שאינה חלקת הדגמה. אלוף יגאל אלון 2 נמסרה
לחברת ההדגמה ב-15.09 ונשארת כך עד החלטת חן (#87): בלעדיה הסריקה באזור
ההדגמה מוסרת אותה ראשונה, והתקרה שלה אינה נכנסת במגרש.

**מתי הוא מסרב:** מסד שאינו על המחשב הזה, או חברה שאינה חברת הדגמה.
במוצר אין ביטול מסירה, וזה נכון; הסקריפט הזה קיים רק למסד ההדגמה המקומי.
"""
import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_parcels as demo  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402
from app.models.package import Balance, Delivery  # noqa: E402
from app.models.tenant import Company  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


async def main(apply: bool) -> int:
    host = urlparse(get_settings().database_url.replace("+asyncpg", "")).hostname
    if host not in LOCAL_HOSTS:
        print(f"מסרב: המסד על {host}, לא על המחשב הזה")
        return 2

    async with AsyncSessionLocal() as s:
        company = (await s.execute(select(Company).where(
            Company.slug.like(f"{demo.COMPANY_SLUG_PREFIX}%")))).scalars().first()
        if company is None:
            print("אין חברת הדגמה במסד")
            return 2

        ids, mixed = {}, []
        for block, parcel, address in demo.DELIVERED + [demo.FOURTH]:
            o = (await s.execute(select(Opportunity).where(
                Opportunity.block == block, Opportunity.parcel == parcel))).scalars().first()
            if o:
                ids[o.id] = address
                if (o.metadata_json or {}).get("planned_unit_mix"):
                    mixed.append(o)
        rows = (await s.execute(select(Delivery).where(
            Delivery.company_id == company.id, Delivery.opportunity_id.in_(list(ids))))).scalars().all()
        balance = (await s.execute(select(Balance).where(Balance.company_id == company.id))).scalar_one()

        print(f"{company.name} · יתרה {balance.credits_remaining} → {demo.STARTING_CREDITS}")
        for r in rows:
            print(f"  מסירה שתימחק: {ids[r.opportunity_id]} · {r.delivered_at.astimezone():%d.%m %H:%M}")
        for o in mixed:
            print(f"  תמהיל שיימחק: {ids[o.id]}")
        if not rows and not mixed and balance.credits_remaining == demo.STARTING_CREDITS:
            print("כבר בנקודת ההתחלה — אין מה לשנות")
            return 0
        if not apply:
            print("\nלא שונה דבר. להרצה: --apply")
            return 1

        await s.execute(delete(Delivery).where(Delivery.id.in_([r.id for r in rows])))
        balance.credits_remaining = demo.STARTING_CREDITS
        for o in mixed:
            o.metadata_json = {k: v for k, v in o.metadata_json.items()
                               if k not in ("planned_unit_mix", "planned_unit_mix_meta")}
        await s.commit()
        print("\nבוצע.")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="איפוס חברת ההדגמה אחרי חזרה")
    ap.add_argument("--apply", action="store_true", help="לבצע, ולא רק להציג")
    sys.exit(asyncio.run(main(ap.parse_args().apply)))
