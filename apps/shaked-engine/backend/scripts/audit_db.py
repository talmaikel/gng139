"""‏ביקורת הנתונים — החלק שנשען על המסד. **קורא בלבד.**

נכתב כדי שהביקורת הלילית תריץ **פקודה אחת** במקום לאלתר שמונה. הגרסה
הקודמת נתנה לסוכן הוראות חופשיות, והוא בנה בכל לילה פקודות `psql` עם
`export $(grep ... .env)` — הצבה בתוך פקודה, שהיא הקטגוריה שתמיד מבקשת
אישור. משימה מתוזמנת שמבקשת אישור בלילה פשוט עומדת עד הבוקר.

שתי תוצאות לוואי טובות: הפקודות מתועדות בגיט ולא מאולתרות, ואפשר
להריץ את אותה בדיקה ביד בלי לעבור על הפרומפט.

    .venv/bin/python scripts/audit_db.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.cities.herzliya.candidates import SORTABLE
from app.core.database import AsyncSessionLocal
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity

# מעל זה ספירת הדירות אינה שמישה. חציון 94, אחוזון 90 הוא 166.
MAX_SQM_PER_UNIT = 200.0
SENTINELS = {999, -1}
TOP = 10


def _assess(o: Opportunity, key: str):
    return ((o.metadata_json or {}).get("assessment") or {}).get(key)


def _ratios(o: Opportunity) -> list[str]:
    """מה שחייב להתקיים פיזית. כל הפרה כאן היא ממצא, לא רעש.

    **הגרסה הראשונה של הפונקציה הזו ייצרה 21 ממצאים, ורובם היו שקר.**
    היא בדקה `cap_400 > שטח המגרש × 5.5` מתוך הנחה שהתקרה היא 400%
    מהמגרש. היא אינה: §70ב(א)(1) קובע 400% מ**השטח הבנוי הקיים**, ולכן
    בניין בן תשע קומות על מגרש קטן מקבל תקרה גבוהה פי עשרה מהמגרש —
    וזה נכון. הבדיקה כאן נשענת על גבול שבאמת אינו ניתן לחציה: שטח בנוי
    אינו יכול לעלות על המגרש כפול מספר הקומות, כלומר תכסית מעל 100%.
    """
    bad = []
    u, a, floors = o.existing_units, o.area_sqm, _assess(o, "floors_low")
    cap = _assess(o, "cap_400_sqm")

    if u in SENTINELS:
        bad.append(f"ספירת דירות היא ערך זקיף ({u})")
    if u and a and u > 0 and a / u > MAX_SQM_PER_UNIT:
        bad.append(f"{a / u:,.0f} מ״ר מגרש לדירה — מעל {MAX_SQM_PER_UNIT:.0f}")

    if cap and a and floors and float(a) > 0 and float(floors) > 0:
        existing = float(cap) / 4          # התקרה היא 400% מהשטח הקיים
        coverage = existing / (float(a) * float(floors))
        if coverage > 1.0:
            bad.append(f"תכסית {coverage:.0%} — שטח בנוי גדול ממגרש × קומות")

    if cap and u and u > 0:
        per_unit = (float(cap) / 4) / u    # שטח בנוי קיים לדירה
        if per_unit < 25:
            bad.append(f"{per_unit:,.0f} מ״ר בנוי לדירה — קטן מדירה אפשרית")
    return bad


async def main() -> int:
    findings: list[str] = []
    async with AsyncSessionLocal() as s:
        # ── ב · ביקורת המיון: לדרג כמו שהלקוח ידרג, ולקרוא את הראש ──
        for name, (col, label) in SORTABLE.items():
            rows = (await s.execute(
                select(Opportunity).where(col.isnot(None))
                .order_by(col.desc()).limit(TOP)
            )).scalars().all()
            print(f"\n── מיון לפי {label} ({name}) · {len(rows)} ראשונות ──")
            for o in rows:
                bad = _ratios(o)
                mark = "  !! " if bad else "     "
                print(f"{mark}{o.block}/{o.parcel}  שטח={o.area_sqm or 0:,.0f}  "
                      f"דירות={o.existing_units}  קומות={_assess(o, 'floors_low')}  "
                      f"תקרה={_assess(o, 'cap_400_sqm')}")
                for b in bad:
                    findings.append(f"{name} · {o.block}/{o.parcel}: {b}")
                    print(f"        → {b}")

        # ── ד · שלמות ──
        async def count(*where):
            return (await s.execute(
                select(func.count()).select_from(Opportunity).where(*where))).scalar_one()

        total = await count()
        no_units = await count(Opportunity.existing_units.is_(None))
        no_cap = await count(Opportunity.metadata_json["assessment"]["cap_400_sqm"].is_(None))
        screenable = await count(
            Opportunity.metadata_json["assessment"]["screenable"].astext == "true")
        deliverable = await count(
            Opportunity.metadata_json["assessment"]["deliverable"].astext == "true")
        archive = (await s.execute(
            select(func.count(func.distinct(FieldEvidence.opportunity_id)))
            .where(FieldEvidence.source_url.like("%complot.co.il%")))).scalar_one()

        print("\n── שלמות ──")
        for k, v in [("סה״כ", total), ("screenable", screenable), ("deliverable", deliverable),
                     ("בלי ספירת דירות", no_units), ("בלי תקרת 400%", no_cap),
                     ("עם ראיית ארכיון", archive)]:
            print(f"     {k:22s} {v}")

        base = {"screenable": 576, "deliverable": 9, "no_units": 39, "no_cap": 0, "archive": 20}
        got = {"screenable": screenable, "deliverable": deliverable,
               "no_units": no_units, "no_cap": no_cap, "archive": archive}
        for k, want in base.items():
            # ‏**כל ירידה היא ממצא.** ראיות הארכיון כבר נמחקו פעם בזריעה
            # מחדש, ושליפה משם יקרה ומוגבלת.
            if got[k] < want:
                findings.append(f"שלמות · {k}: {got[k]} מול בסיס {want} — ירידה")

    print("\n" + ("=" * 50))
    if findings:
        print(f"⚠️  {len(findings)} ממצאים")
        for f in findings:
            print("  ·", f)
    else:
        print("✅ אין ממצאים במסד")
    print(json.dumps({"findings": findings}, ensure_ascii=False))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
