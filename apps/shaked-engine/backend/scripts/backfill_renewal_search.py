"""‏W5 · חיפוש אינטרנט אוטומטי לחלוטין, לחלקות שאין להן תוצאה טרייה. (#127)

    .venv/bin/python scripts/backfill_renewal_search.py                 # 25 הבאות בתור
    .venv/bin/python scripts/backfill_renewal_search.py --limit 10
    .venv/bin/python scripts/backfill_renewal_search.py <id> <id> ...   # מזהים מפורשים

בלי חלקה אחת לא נבדקת ידנית: הרשימה היא כל חלקה שאין לה עדיין ראיית
`renewal_web_search` שהסתיימה בהצלחה (לא `retryable`) ולא פגה — כולל חלקה
חדשה שמעולם לא נבדקה, וחלקה שהבדיקה הקודמת שלה נכשלה (timeout/API) ומחכה
לניסיון חוזר. ‏`renewal_search.enrich()` בודק את זה שוב לכל חלקה, כך
שהרשימה כאן היא רק אופטימיזציה שלא לבחור שוב מה שכבר טרי.

בלי `BRAVE_SEARCH_API_KEY` כל בדיקה תחזור `retryable` — הסקריפט ירוץ,
אבל שום חלקה לא תיקבע כ״נקייה״ עד שיהיה מפתח (ראו .env.example).
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.cities.herzliya import renewal_search  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.evidence import FieldEvidence  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402


async def _next_batch(session, city: str, limit: int) -> list[UUID]:
    """הזדמנויות שאין להן עדיין ראיית חיפוש שהסתיימה בהצלחה ולא פגה."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().source_max_age_days)
    fresh = select(FieldEvidence.opportunity_id).where(
        FieldEvidence.field == renewal_search.FIELD,
        FieldEvidence.value["status"].astext != "retryable",
        FieldEvidence.retrieved_at >= cutoff)
    stmt = (select(Opportunity.id)
            .where(Opportunity.city_code == city, Opportunity.id.notin_(fresh))
            .order_by(Opportunity.block, Opportunity.parcel)
            .limit(limit))
    return list((await session.execute(stmt)).scalars().all())


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*", help="מזהי הזדמנות מפורשים; בלי זה — הבאים בתור")
    ap.add_argument("--city", default="herzliya")
    ap.add_argument("--limit", type=int, default=renewal_search.MAX_SHORTLIST)
    a = ap.parse_args(argv)
    if a.limit > renewal_search.MAX_SHORTLIST:
        ap.error(f"--limit לא יכול לעלות על {renewal_search.MAX_SHORTLIST}")

    async with AsyncSessionLocal() as session:
        ids = [UUID(x) for x in a.ids] if a.ids else await _next_batch(session, a.city, a.limit)
        if not ids:
            print("אין חלקות שממתינות לבדיקה")
            return 0
        out = await renewal_search.enrich(session, ids)
        await session.commit()

    print(f"נבדקו {out['checked']} מתוך {len(ids)}")
    print(f"  אומתו כמחודשות: {out['verified_renewed']}")
    print(f"  לא נמצא סימן: {out['no_automated_renewal_signal']}")
    print(f"  לא הסתיימו (ינוסו שוב בהרצה הבאה): {out['retryable']}")
    print(f"  היו טריות ולא נבדקו שוב: {out['skipped_fresh']}")
    print(f"  בלי כתובת עם מספר בית: {out['skipped_no_address']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
