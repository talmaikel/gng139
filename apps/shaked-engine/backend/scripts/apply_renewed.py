"""‏W5 · כותב `renewal_status` לכל החלקות ומחשב מחדש את ההערכה — בלי זריעה.

    .venv/bin/python scripts/apply_renewed.py            # מראה מה ישתנה, ולא משנה
    .venv/bin/python scripts/apply_renewed.py --apply    # משנה

ההכרעה לכל חלקה: החלטת צוות מהמסך, אחריה `data/verified_renewed.json`,
ואחריה הסימנים (`renewal_signals.py`). מסד בלבד — אין פנייה לארכיון.

**וגם השורות העיוורות.** ‏`strengthened`/`occupied` נגזרו מ״ארוע אחרון להצגה״
כאילו היה תיאור הבקשה. הן מומרות ל-`tama38_event` — אמת אם אחת מהן הייתה
אמת, כי זו בדיוק התאמת הביטוי לארוע — ונמחקות. בלי זה התיק ממשיך לכתוב
״לא נמצאה בקשת חיזוק עם היתר״ על סמך עמודה שאינה מציגה בקשות.

**הרצה יבשה אינה כותבת כלל:** הטרנזקציה נפתחת READ ONLY.
"""
import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_parcels as demo  # noqa: E402
from sqlalchemy import delete, select, text  # noqa: E402

from app.cities.herzliya import renewal  # noqa: E402
from app.cities.herzliya.archive_facts import RETIRED_FIELDS  # noqa: E402
from app.cities.herzliya.assessments import refresh  # noqa: E402
from app.cities.herzliya.rules import HerzliyaCityRules  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.evidence import Certainty  # noqa: E402
from app.models.evidence import FieldEvidence  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402

ARCHIVE_HOST = "complot.co.il"
LABEL = {"verified_renewed": "אומת כמחודש", "suspected": "חשוד", "none": "לא נמצא סימן",
         "unknown": "לא ידוע (אין היתרי תיק)"}


async def retire_blind_rows(session, write: bool) -> dict:
    """‏`strengthened`/`occupied` מהתיק → ‏`tama38_event`. מחזיר גם מה הרצה יבשה מניחה."""
    rows = (await session.execute(select(FieldEvidence).where(
        FieldEvidence.field.in_(RETIRED_FIELDS),
        FieldEvidence.source_url.like(f"%{ARCHIVE_HOST}%")))).scalars().all()
    by_opp = defaultdict(list)
    for r in rows:
        by_opp[r.opportunity_id].append(r)
    has = set((await session.execute(select(FieldEvidence.opportunity_id).where(
        FieldEvidence.field == "tama38_event"))).scalars().all())

    extra_for, hits = {}, 0
    for oid, rs in by_opp.items():
        hit = any(r.value is True for r in rs)
        hits += hit
        if oid in has:
            continue
        extra_for[oid] = {"tama38_event": hit}
        if write:
            src = max(rs, key=lambda r: r.retrieved_at)
            session.add(FieldEvidence(
                opportunity_id=oid, field="tama38_event", value=hit,
                certainty=Certainty.DERIVED.value, source_url=src.source_url,
                retrieved_at=src.retrieved_at, location=src.location,
                method="ארוע אחרון בבקשה מזכיר תמ״א 38 או חיזוק · הומר מקריאה קודמת"))
    if write and rows:
        await session.execute(delete(FieldEvidence).where(
            FieldEvidence.id.in_([r.id for r in rows])))
        await session.flush()
    return {"rows": len(rows), "parcels": len(by_opp), "tama38_true": hits,
            "extra_for": {} if write else extra_for}


async def main(apply: bool, city: str = "herzliya") -> int:
    async with AsyncSessionLocal() as s:
        if not apply:
            await s.execute(text("SET TRANSACTION READ ONLY"))
        ready = {(o.block, o.parcel): o for o in (await s.execute(
            select(Opportunity).where(Opportunity.city_code == city))).scalars().all()}

        blind = await retire_blind_rows(s, apply)
        out = await renewal.apply_all(s, city, write=apply, extra_for=blind["extra_for"])
        c = out["counts"]

        print(f"{'כותב' if apply else 'הרצה יבשה — לא נכתב דבר'} · {out['total']} חלקות")
        print(f"  שורות strengthened/occupied מהתיק: {blind['rows']} ב-{blind['parcels']} חלקות"
              f" · מומרות ל-tama38_event (אמת ב-{blind['tama38_true']}) ונמחקות")
        for k in ("verified_renewed", "suspected", "none", "unknown"):
            print(f"  {LABEL[k]}: {c.get(k, 0)}")
        print(f"  מהרשימה או מהצוות: {c['manual']} · החלטות צוות שנשמרו: {c['team_kept']}"
              f" · סטטוס שמשתנה מול המסד: {c['changed']}")

        was_ready = 0
        for f in out["flagged"]:
            o = ready.get(tuple(f["key"].split("/")))
            a = ((o.metadata_json or {}).get("assessment") or {}) if o else {}
            was_ready += bool(a.get("deliverable"))
            print(f"  · {f['key']} {f['address']} — {LABEL[f['status']]}"
                  f"{' · מוכנה למסירה היום' if a.get('deliverable') else ''}"
                  f" · {' · '.join(f['reasons'])}")
        print(f"  מוכנות היום שייעצרו: {was_ready}")
        # מוכנה היום ובלי הכרעה — השער ייפתח, והמסירה תשלים אותו (מהמסד, או בשליפה)
        blind_ready = sorted(k for k, st in out["by_key"].items() if st == "unknown" and (
            ((ready[tuple(k.split("/"))].metadata_json or {}).get("assessment") or {}).get("deliverable")))
        print(f"  מוכנות היום שיישארו בלי הכרעה: {len(blind_ready)}"
              + (f" · {', '.join(blind_ready)}" if blind_ready else ""))

        flagged = {f["key"]: f for f in out["flagged"]}
        for block, parcel, address in demo.DELIVERED:
            f = flagged.get(f"{block}/{parcel}")
            print(f"  חלקת הדגמה {block}/{parcel} {address}: "
                  f"{LABEL[f['status']] if f else 'אינה מסומנת'}")

        if not apply:
            # בלי commit: סגירת הסשן מגלגלת לאחור, וממילא לא נכתב דבר
            print("להחלה: --apply")
            return 1
        counts = await refresh(s, HerzliyaCityRules(), city)
        await s.commit()
        print(f"  ההערכה חושבה מחדש: {counts}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="לכתוב. בלי זה — הרצה יבשה")
    ap.add_argument("--city", default="herzliya")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.apply, a.city)))
