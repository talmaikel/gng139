"""‏ביקורת הנתונים — החלק שנשען על המסד. **קורא בלבד.**

נכתב כדי שהביקורת הלילית תריץ **פקודה אחת** במקום לאלתר שמונה. הגרסה
הקודמת נתנה לסוכן הוראות חופשיות, והוא בנה בכל לילה פקודות `psql` עם
`export $(grep ... .env)` — הצבה בתוך פקודה, שהיא הקטגוריה שתמיד מבקשת
אישור. משימה מתוזמנת שמבקשת אישור בלילה פשוט עומדת עד הבוקר.

שתי תוצאות לוואי טובות: הפקודות מתועדות בגיט ולא מאולתרות, ואפשר
להריץ את אותה בדיקה ביד בלי לעבור על הפרומפט.

    .venv/bin/python scripts/audit_db.py
"""
import argparse
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

# **השטח הבנוי נקרא מהראיה ולא מההערכה.** הגרסה הראשונה גזרה אותו מ-
# ‏`cap_400_sqm / 4`, כלומר מתוך ההערכה השמורה — ולכן כשההערכה נמחקה,
# הבדיקה שהייתה תופסת את הספירות השבורות פשוט לא רצה, בדיוק ברגע
# שהמסד היה במצב הגרוע ביותר. הראיה `existing_area` קיימת ל-699 תמיד.
EXISTING_AREA = "existing_area"

# מעל זה ספירת הדירות אינה שמישה. חציון 94, אחוזון 90 הוא 166.
MAX_SQM_PER_UNIT = 200.0
MIN_SQM_PER_UNIT = 25.0
SENTINELS = {999, -1}
TOP = 10


def _assess(o: Opportunity, key: str):
    return ((o.metadata_json or {}).get("assessment") or {}).get(key)


def _ratios(o: Opportunity, built: float | None = None) -> list[str]:
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
    if built is None and (cap := _assess(o, "cap_400_sqm")):
        built = float(cap) / 4             # התקרה היא 400% מהשטח הקיים

    if u in SENTINELS:
        bad.append(f"ספירת דירות היא ערך זקיף ({u})")

    # **שני הסימנים הם על אותו יחס, בשני כיוונים.** ‏`usable_units`
    # פוסל מעל 200 מ״ר בנוי לדירה — שם הספירה נמוכה מדי (בניין בן 15
    # קומות שרשום כארבע דירות). מתחת ל-25 היא גבוהה מדי, וזה כיוון
    # שלא נבדק עד 14.09: גורדון 7 נושא 99 דירות על 553 מ״ר בנוי.
    if built and u and u > 0:
        per_unit = built / u
        if per_unit > MAX_SQM_PER_UNIT:
            bad.append(f"{per_unit:,.0f} מ״ר בנוי לדירה — מעל {MAX_SQM_PER_UNIT:.0f}")
        elif per_unit < MIN_SQM_PER_UNIT:
            bad.append(f"{per_unit:,.0f} מ״ר בנוי לדירה — קטן מדירה אפשרית")

    if built and a and floors and float(a) > 0 and float(floors) > 0:
        coverage = built / (float(a) * float(floors))
        if coverage > 1.0:
            bad.append(f"תכסית {coverage:.0%} — שטח בנוי גדול ממגרש × קומות")
    return bad


async def main(args) -> int:
    findings: list[str] = []
    fatal: list[str] = []
    async with AsyncSessionLocal() as s:
        built = {
            e.opportunity_id: float(e.value)
            for e in (await s.execute(
                select(FieldEvidence).where(FieldEvidence.field == EXISTING_AREA))).scalars()
            if e.value not in (None, "")
        }
        # ── ב · ביקורת המיון: לדרג כמו שהלקוח ידרג, ולקרוא את הראש ──
        for name, (col, label) in SORTABLE.items():
            rows = (await s.execute(
                select(Opportunity).where(col.isnot(None))
                .order_by(col.desc()).limit(TOP)
            )).scalars().all()
            print(f"\n── מיון לפי {label} ({name}) · {len(rows)} ראשונות ──")
            for o in rows:
                bad = _ratios(o, built.get(o.id))
                mark = "  !! " if bad else "     "
                b = built.get(o.id)
                print(f"{mark}{o.block}/{o.parcel}  מגרש={o.area_sqm or 0:,.0f}  "
                      f"בנוי={b and f'{b:,.0f}' or '—'}  דירות={o.existing_units}  "
                      f"קומות={_assess(o, 'floors_low')}  תקרה={_assess(o, 'cap_400_sqm')}")
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

        # ── שערי CI ──
        #
        # מופרדים מ-`findings` **בכוונה**. ממצא הוא ״מספר נראה מוזר״ —
        # מדווחים ומסתכלים. שער הוא ״המוצר אינו עובד״ — אין מה לשקול.
        # ב-14.09.2026 כל 699 ההזדמנויות איבדו את ההערכה השמורה כי
        # הזריעה רצה בלי שלב ההערכה, ואף בדיקה לא נצבעה באדום: המסך
        # היה מציג רשימה ריקה ליזם, בלי שגיאה ובלי סימן.
        if args.require_assessment and total:
            without = await count(Opportunity.metadata_json["assessment"].is_(None))
            if without:
                fatal.append(
                    f"{without} מתוך {total} הזדמנויות בלי ההערכה השמורה. "
                    "הזריעה רצה בלי שלב ההערכה — ההצלה היא "
                    "`refresh()` מ-app/cities/herzliya/assessments.py")
        if total and deliverable < args.min_deliverable:
            fatal.append(
                f"ניתנים למסירה: {deliverable}, מתחת לרצפה {args.min_deliverable}. "
                "אין מה למסור ללקוח.")
        if total and screenable < args.min_screenable:
            fatal.append(
                f"נשארים במסלול: {screenable}, מתחת לרצפה {args.min_screenable}.")

        print("\n── שלמות ──")
        for k, v in [("סה״כ", total), ("screenable", screenable), ("deliverable", deliverable),
                     ("בלי ספירת דירות", no_units), ("בלי תקרת 400%", no_cap),
                     ("עם ראיית ארכיון", archive)]:
            print(f"     {k:22s} {v}")

        # ‏W5 · 16.09 · deliverable 9 → 5 בכוונה: 6537/120, 6536/501, 6531/156 ו-6531/152
        # חשודות כמחודשות וממתינות לצוות. זו אינה ירידה אלא עצירה.
        base = {"screenable": 576, "deliverable": 5, "no_units": 39, "no_cap": 0, "archive": 20}
        got = {"screenable": screenable, "deliverable": deliverable,
               "no_units": no_units, "no_cap": no_cap, "archive": archive}
        for k, want in base.items():
            # ‏**כל ירידה היא ממצא.** ראיות הארכיון כבר נמחקו פעם בזריעה
            # מחדש, ושליפה משם יקרה ומוגבלת.
            if got[k] < want:
                findings.append(f"שלמות · {k}: {got[k]} מול בסיס {want} — ירידה")

    print("\n" + ("=" * 50))
    if fatal:
        print(f"🟥 {len(fatal)} כשלים חוסמים")
        for f in fatal:
            print("  ·", f)
    if findings:
        print(f"⚠️  {len(findings)} ממצאים")
        for f in findings:
            print("  ·", f)
    if not fatal and not findings:
        print("✅ אין ממצאים במסד")
    print(json.dumps({"fatal": fatal, "findings": findings}, ensure_ascii=False))

    # ‏2 = המוצר שבור · 1 = יש מה להסתכל עליו · 0 = נקי.
    # שני קודים ולא אחד, כדי שה-CI יוכל להיכשל על השני ולא על הראשון:
    # ממצא שמפיל בנייה מאמן אנשים להתעלם מהבדיקה.
    return 2 if fatal else (1 if findings else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ביקורת נתונים — קריאה בלבד")
    ap.add_argument("--require-assessment", action="store_true",
                    help="כשל חוסם אם הזדמנות כלשהי חסרת ההערכה השמורה")
    ap.add_argument("--min-deliverable", type=int, default=0,
                    help="רצפה לכמות הניתנים למסירה; מתחתיה כשל חוסם")
    ap.add_argument("--min-screenable", type=int, default=0,
                    help="רצפה לכמות הנשארים במסלול המגרשי")
    sys.exit(asyncio.run(main(ap.parse_args())))
