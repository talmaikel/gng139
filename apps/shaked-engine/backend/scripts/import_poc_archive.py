"""מועד ההיתר מתיקי הבניין שסריקת הארכיון של ה-POC כבר שלפה — בלי פנייה לארכיון.

    .venv/Scripts/python scripts/import_poc_archive.py            # מראה מה ייכתב, ולא כותב
    .venv/Scripts/python scripts/import_poc_archive.py --apply    # כותב, מעריך מחדש ומייצא

‏567 מ-576 המועמדים שבמסלול חסומים רק על `permit_date`, ורק תיק הבניין עונה
עליו. ‏`POC/data/shaked.sqlite3` מחזיק תיקים שנשלפו במלואם (`metadata_complete`),
עם טבלת הבקשות של אותו עמוד ש-`archive_facts.parse_requests` קורא — ובלי
עמודת שם המבקש. העובדות נגזרות באותה `facts()`, ונכתבות באותה `_write()`.

**רק מה שתיק חסר לא יכול להפוך.** הסריקה לא הגיעה לכל התיקים, ולחלקה עשוי
להיות תיק נוסף שלא נשלף. השנה המוקדמת ביותר יכולה רק לרדת כשמתווסף תיק,
ולכן היתר לפני 1980 נשאר ״עבר״ — ונכתב. היתר מאוחר יותר עלול להתברר כמוקדם,
ואינו נכתב: נשאר שאלה פתוחה, שהשליפה ברגע המסירה עונה עליה. מאותה סיבה
הדגלים הבוליאניים נכתבים רק כשהם אמת.
"""
import argparse
import asyncio
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

from app.cities.herzliya import renewal  # noqa: E402
from app.cities.herzliya.archive_facts import MAX_TIKS, _write, export_fetched, facts  # noqa: E402
from app.cities.herzliya.assessments import refresh  # noqa: E402
from app.cities.herzliya.rules import HerzliyaCityRules  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.opportunity import Opportunity  # noqa: E402

POC_DB = Path(__file__).resolve().parents[4] / "POC" / "data" / "shaked.sqlite3"
REQUESTS_HEADER = "מספר בקשה"
SAFE_BEFORE_YEAR = 1980
TRUE_ONLY = ("post_2005_permit", "tama38_event", "representative_event")


def _requests(payload: dict) -> list[dict]:
    """שורות טבלת הבקשות, בצורה ש-`facts()` מצפה לה. שם המבקש אינו בטבלה."""
    for t in payload.get("tables") or []:
        h = t.get("headers") or []
        if h and h[0] == REQUESTS_HEADER:
            col = {name: i for i, name in enumerate(h)}
            return [{"req": r[0],
                     "last_event": r[col["ארוע אחרון להצגה"]] if "ארוע אחרון להצגה" in col else "",
                     "permit_date": r[col["תאריך היתר"]] if "תאריך היתר" in col else ""}
                    for r in t.get("rows") or [] if r and str(r[0]).isdigit()]
    return []


def load_poc(path: Path = POC_DB) -> dict[tuple[str, str], list[dict]]:
    """תיקים שנשלפו במלואם, לפי גוש/חלקה."""
    con = sqlite3.connect(path)
    by_parcel = defaultdict(list)
    for (raw,) in con.execute("select payload from archive_files where state = 'metadata_complete'"):
        p = json.loads(raw)
        for gp in p.get("parcels") or []:
            by_parcel[(str(gp["gush"]), str(gp["parcel"]))].append(p)
    con.close()
    return by_parcel


def safe_facts(files: list[dict]) -> dict | None:
    files = sorted(files, key=lambda p: int(p.get("file_number") or 0))[:MAX_TIKS]
    f = facts([r for p in files for r in _requests(p)])
    if f["earliest_year"] is None or f["earliest_year"] >= SAFE_BEFORE_YEAR:
        return None
    for k in TRUE_ONLY:
        if f.get(k) is not True:
            f[k] = None
    return f


async def main(apply: bool, city: str = "herzliya") -> int:
    poc = load_poc()
    counts = Counter()
    async with AsyncSessionLocal() as s:
        if not apply:
            await s.execute(text("SET TRANSACTION READ ONLY"))
        opps = (await s.execute(select(Opportunity).where(Opportunity.city_code == city))).scalars().all()
        for opp in opps:
            a = (opp.metadata_json or {}).get("assessment") or {}
            if "permit_date" not in (a.get("threshold_open") or []):
                continue
            counts["permit_open"] += 1
            files = poc.get((str(opp.block), str(opp.parcel)))
            if not files:
                continue
            counts["in_poc"] += 1
            f = safe_facts(files)
            if f is None:
                counts["left_open (1980+)"] += 1
                continue
            counts["written"] += 1
            print(f"  {opp.block}/{opp.parcel} · {opp.address} · היתר {f['earliest_year']}")
            if apply:
                tiks = [str(p["file_number"]) for p in sorted(files, key=lambda p: int(p.get("file_number") or 0))]
                await _write(s, opp.id, f, files[0], tiks[:MAX_TIKS], len(tiks))
                await renewal.apply(s, opp)
        print(dict(counts))
        if not apply:
            print("להחלה: --apply")
            return 1
        before = sum(1 for o in opps if ((o.metadata_json or {}).get("assessment") or {}).get("deliverable"))
        out = await refresh(s, HerzliyaCityRules(), city)
        await s.commit()
        print(f"  deliverable: {before} → {out.get('deliverable')} · {out}")
        print(f"  ייצוא: {await export_fetched(s, city)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="מועד היתר מסריקת הארכיון של ה-POC")
    ap.add_argument("--apply", action="store_true", help="לכתוב. בלי זה — הרצה יבשה")
    ap.add_argument("--city", default="herzliya")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.apply, a.city)))
