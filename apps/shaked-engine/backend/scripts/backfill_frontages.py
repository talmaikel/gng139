"""‏W1 · כותב את מספר החזיתות לרחוב לחלקות שכבר זרועות, ומחשב מחדש את ההערכה.

    .venv/bin/python scripts/backfill_frontages.py            # מראה מה ייכתב, ולא כותב
    .venv/bin/python scripts/backfill_frontages.py --apply    # כותב, ומריץ את ההערכה לכל העיר

השטח לפי המדיניות צריך לדעת אם המגרש פינתי: בשתי חזיתות יש קו קדמי ונסיגות.
הזריעה כותבת את השדה מעכשיו, אבל זריעה מחדש מוחקת ומשחזרת את כל הראיות — וזה
מיותר כדי להוסיף שדה אחד. מסד בלבד: בלי רשת ובלי ארכיון.
"""
import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.cities.herzliya import assessments  # noqa: E402
from app.cities.herzliya.rules import HerzliyaCityRules  # noqa: E402
from app.cities.herzliya.seed_layer_a import _load, street_frontages  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.evidence import Certainty  # noqa: E402
from app.models.evidence import FieldEvidence  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402


async def main(apply: bool) -> None:
    front = {x["key"]: x for x in _load("frontages_v2.json")}
    src = _load("source_fetched.json")["govmap_parcels"]
    counts = {"written": 0, "already": 0, "no_frontage": 0, "corner": 0}
    async with AsyncSessionLocal() as session:
        have = set((await session.execute(
            select(FieldEvidence.opportunity_id).where(FieldEvidence.field == "street_frontages"))).scalars())
        opps = (await session.execute(
            select(Opportunity).where(Opportunity.city_code == "herzliya"))).scalars().all()
        for o in opps:
            if o.id in have:
                counts["already"] += 1
                continue
            key = f"{o.block}/{o.parcel}"
            value = street_frontages(front.get(key, {}))
            if value is None:
                counts["no_frontage"] += 1
            elif value >= 2:
                counts["corner"] += 1
            session.add(FieldEvidence(
                opportunity_id=o.id, field="street_frontages", value=value,
                certainty=(Certainty.DERIVED if value is not None else Certainty.MISSING).value,
                source_url=src["url"], retrieved_at=datetime.fromisoformat(src["retrieved_at"]),
                location=f"גוש {o.block} חלקה {o.parcel} · חזיתות לרחוב",
                method=("מספר החזיתות לרחוב ב-frontages_v2; שתיים ומעלה = מגרש פינתי"
                        if value is not None else "המקור נבדק והשדה ריק בו")))
            counts["written"] += 1
        print(counts)
        if not apply:
            await session.rollback()
            print("לא נכתב דבר. להרצה: --apply")
            return
        await session.flush()
        print(await assessments.refresh(session, HerzliyaCityRules()))
        await session.commit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    asyncio.run(main(ap.parse_args().apply))
