"""‏A21 · רשימת הבדיקה לפני ההדגמה — כפקודה, לא כזיכרון. **קורא בלבד.**

    .venv/bin/python scripts/demo_preflight.py

כל בדיקה כאן היא משהו שנשבר, או כמעט נשבר, בשבוע שלפני ההדגמה:

- **השרת רץ מהתיקייה הנכונה ועל הקוד של היום.** ביום שני השרת רץ מתיקייה
  של אתמול, והפרונט של היום דיבר עם הקוד של אתמול. ‏uvicorn בלי ‎--reload
  אינו רואה מיזוג — שרת שעלה לפני הקומיט האחרון מריץ קוד ישן.
- **היתרה 3 ואף חלקת הדגמה לא נמסרה.** החזרה ביום רביעי בבוקר מוסרת את
  שלוש החלקות ומאפסת את היתרה; בלי איפוס, שלב המסירה בהדגמה נכשל.
- **החלקות מוכנות למסירה.** מועמד לא מוכן נשלף מהארכיון בזמן אמת: 10–20
  שניות, ואפשרות לסירוב.
- **מסך = PDF = אקסל** על ארבע החלקות — אותה בדיקה שה-CI מריץ (B14).
- **ההתחברות תחזיק.** טוקן של שעה שהונפק בבוקר פג באמצע ההדגמה; סוד JWT
  ריק מתחלף בכל הפעלה מחדש של השרת ומנתק את כולם.
- **המנהרה.** הכתובת ציבורית לכל מי שיש לו אותה; פתוחה רק בזמן ההדגמה.

‏0 = מוכן · 1 = יש אזהרות, אפשר להתחיל · 2 = לא להתחיל.
"""
import asyncio
import datetime as dt
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
REPO = BACKEND.parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_parcels as demo  # noqa: E402

OK, WARN, BLOCK = "✓", "!", "✗"
results: list[tuple[str, str, str]] = []


def report(level: str, title: str, detail: str = "") -> None:
    results.append((level, title, detail))


def sh(*cmd: str, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ── קוד ותהליכים ──

def check_code() -> None:
    sh("git", "fetch", "-q", "origin", "main", cwd=REPO)
    head, remote = sh("git", "rev-parse", "HEAD", cwd=REPO), sh("git", "rev-parse", "origin/main", cwd=REPO)
    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=REPO)
    if branch != "main":
        report(BLOCK, f"הריפו על הענף {branch}, לא על main", "git checkout main && git pull")
    elif head != remote:
        report(BLOCK, "הקוד המקומי אינו main העדכני", "git pull --ff-only")
    else:
        report(OK, "הקוד המקומי הוא main העדכני", head[:7])
    dirty = sh("git", "status", "--porcelain", "--", "apps/shaked-engine", cwd=REPO)
    if dirty:
        report(WARN, "יש שינויים שלא נשמרו בקוד המוצר", dirty.splitlines()[0])


def _listener(port: int) -> tuple[str, Path | None, dt.datetime | None]:
    pid = sh("lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t").split("\n")[0]
    if not pid:
        return "", None, None
    cwd = next((line[1:] for line in sh("lsof", "-a", "-p", pid, "-d", "cwd", "-Fn").splitlines()
                if line.startswith("n")), None)
    started = sh("ps", "-o", "lstart=", "-p", pid)
    try:
        when = dt.datetime.strptime(" ".join(started.split()), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        when = None
    return pid, Path(cwd).resolve() if cwd else None, when


def _last_commit(path: Path) -> dt.datetime | None:
    ts = sh("git", "log", "-1", "--format=%ct", "--", str(path), cwd=REPO)
    return dt.datetime.fromtimestamp(int(ts)) if ts else None


def check_processes() -> None:
    for port, where, name, reloads in ((8000, BACKEND, "השרת", False), (3000, FRONTEND, "שרת המסכים", True)):
        pid, cwd, started = _listener(port)
        if not pid:
            report(BLOCK, f"{name} אינו רץ על פורט {port}")
            continue
        if cwd != where:
            report(BLOCK, f"{name} רץ מתיקייה אחרת", f"{cwd} — צריך {where}")
            continue
        last = _last_commit(where)
        if not reloads and started and last and started < last:
            report(BLOCK, f"{name} עלה לפני הקומיט האחרון ומריץ קוד ישן",
                   f"עלה {started:%d.%m %H:%M}, קומיט {last:%d.%m %H:%M} — להפעיל מחדש")
        else:
            report(OK, f"{name} רץ מהתיקייה הנכונה", f"pid {pid}")


def check_http() -> None:
    def get(url: str) -> int:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except OSError:
            return 0

    if get("http://127.0.0.1:8000/health") == 200:
        report(OK, "השרת עונה")
    else:
        report(BLOCK, "השרת אינו עונה ב-/health")
    # דרך המסכים: 401 פירושו שהבקשה עברה את Next והגיעה לשרת, שדרש התחברות
    code = get("http://127.0.0.1:3000/api/v1/auth/users/me")
    if code == 401:
        report(OK, "שרת המסכים מעביר בקשות לשרת")
    else:
        report(BLOCK, "שרת המסכים אינו מגיע לשרת", f"‏/api/v1/auth/users/me החזיר {code or 'אין חיבור'}")


def check_migrations() -> None:
    alembic = str(BACKEND / ".venv" / "bin" / "alembic")
    current = sh(alembic, "current", cwd=BACKEND).split()
    heads = sh(alembic, "heads", cwd=BACKEND).split()
    if current and heads and current[0] == heads[0]:
        report(OK, "המסד במיגרציה האחרונה", heads[0])
    else:
        report(BLOCK, "המסד אינו במיגרציה האחרונה", ".venv/bin/alembic upgrade head")


def check_auth() -> None:
    from app.core.config import get_settings
    s = get_settings()
    if len(s.jwt_secret or "") < 16:
        report(BLOCK, "אין JWT_SECRET קבוע ב-.env",
               "כל הפעלה מחדש של השרת תנתק את כל המחוברים")
    hours = s.jwt_lifetime_seconds / 3600
    if hours < 3:
        report(WARN, f"התחברות מחזיקה {hours:g} שעות בלבד",
               "להתחבר מחדש בחלון גלישה בסתר פחות משעה לפני שמתחילים")
    else:
        report(OK, f"התחברות מחזיקה {hours:g} שעות")


def check_tunnel() -> None:
    running = sh("pgrep", "-fl", "cloudflared")
    if running:
        report(WARN, "מנהרת cloudflared פתוחה",
               "הכתובת ציבורית — להשאיר רק בזמן ההדגמה, ולסגור מיד אחריה")
    else:
        report(OK, "אין מנהרה פתוחה", "לפתוח רגע לפני: cloudflared tunnel --url http://localhost:3000")


# ── נתונים ──

async def check_data() -> None:
    from sqlalchemy import select

    from app.cities.herzliya import exports
    from app.cities.herzliya.candidates import screen_herzliya_candidates
    from app.cities.herzliya.dossier import assemble
    from app.cities.herzliya.rules import HerzliyaCityRules
    from app.cities.herzliya.surfaces import compare
    from app.core.database import AsyncSessionLocal
    from app.models.opportunity import Opportunity
    from app.models.package import Balance
    from app.models.tenant import Company
    from app.services.deliveries import delivered_ids

    rules = HerzliyaCityRules()
    wanted = demo.DELIVERED + [demo.FOURTH]
    async with AsyncSessionLocal() as s:
        company = (await s.execute(select(Company).where(
            Company.slug.like(f"{demo.COMPANY_SLUG_PREFIX}%")))).scalars().first()
        if company is None:
            report(BLOCK, "אין חברת הדגמה במסד")
            return
        credits = (await s.execute(select(Balance.credits_remaining)
                                   .where(Balance.company_id == company.id))).scalar()
        owned = await delivered_ids(s, company.id)

        opps = {}
        for block, parcel, address in wanted:
            o = (await s.execute(select(Opportunity).where(
                Opportunity.block == block, Opportunity.parcel == parcel))).scalars().first()
            if o is None:
                report(BLOCK, f"{address} ({block}/{parcel}) אינה במסד")
            else:
                opps[(block, parcel)] = o

        already = [a for b, p, a in wanted if (b, p) in opps and opps[(b, p)].id in owned]
        if credits != demo.STARTING_CREDITS or already:
            report(BLOCK, "חברת ההדגמה אינה בנקודת ההתחלה",
                   f"יתרה {credits}, צריך {demo.STARTING_CREDITS}"
                   + (f" · כבר נמסרו: {', '.join(already)}" if already else "")
                   + " — .venv/bin/python scripts/demo_reset.py --apply")
        else:
            report(OK, f"חברת ההדגמה ביתרה {credits}, אף חלקת הדגמה לא נמסרה")

        # המסך שהמציג יראה: אותו אזור, אותם תנאים, בלי מה שכבר נמסר
        rows = await screen_herzliya_candidates(s, {
            "polygon": demo.area_polygon(), "limit": 100, "min_units": demo.MIN_UNITS,
            "preferences": [{"field": demo.SORT_FIELD, "direction": "desc"}],
            "exclude_delivered_ids": owned})
        listed = {(r["block"], r["parcel"]): i + 1 for i, r in enumerate(rows)}
        for block, parcel, address in wanted:
            if (block, parcel) not in opps:
                continue
            o = opps[(block, parcel)]
            a = (o.metadata_json or {}).get("assessment") or {}
            where = listed.get((block, parcel))
            if not a.get("deliverable"):
                report(BLOCK, f"{address} אינה מוכנה למסירה",
                       "המסירה תשלוף תיק מהארכיון בזמן ההדגמה")
            elif where is None and o.id not in owned:
                report(BLOCK, f"{address} אינה ברשימה שהמסך יציג", "האזור או התנאים השתנו")
            else:
                d = await assemble(s, rules, o, None)
                problems = compare(d, exports.excel(d), exports.pdf(d))
                stale = d.get("stale_fields") or []
                if problems:
                    report(BLOCK, f"{address}: המסך, ה-PDF והאקסל אינם מסכימים", problems[0])
                elif stale:
                    report(BLOCK, f"{address}: יש מקורות שהתיישנו", ", ".join(stale))
                else:
                    report(OK, f"{address} מוכנה · שורה {where} ברשימה · מסך = PDF = אקסל",
                           f"{len(d['economics'].get('caveats') or [])} סייגים בתיק")
        await s.rollback()


def check_rendering() -> None:
    """השרת שולח סייגים ותקרת היטל; השאלה אם מישהו מציג אותם (C14, B13)."""
    page = (FRONTEND / "src" / "app" / "dossier" / "[id]" / "page.tsx").read_text(encoding="utf-8")
    export = (BACKEND / "app" / "cities" / "herzliya" / "exports.py").read_text(encoding="utf-8")
    import re
    # ‏`betterment` ולא `betterment_levy_ils`: השני הוא בדיוק שורת ״0 ₪״
    # שצריכה להתחלף. הגרסה הראשונה חיפשה את המילה, ומצאה אותה שם.
    for where, text, needle, task in (
            ("המסך", page, "caveats", "C14"), ("המסך", page, "betterment", "C14"),
            ("הייצוא", export, "caveats", "B13"), ("הייצוא", export, "betterment", "B13")):
        what = "הסייגים" if needle == "caveats" else "תקרת ההיטל"
        if re.search(rf"\b{needle}\b(?!_)", text):
            report(OK, f"{where} מציג את {what}")
        else:
            report(WARN, f"{where} עוד לא מציג את {what}",
                   f"{task} לא מוזג — {'״היטל השבחה 0 ₪״ עדיין מוצג' if needle == 'betterment' else 'הרווח מוצג בלי סייג'}")


MANUAL = [
    "להתחבר מחדש בחלון גלישה בסתר, פחות משעה לפני שמתחילים — לא דרך הסקריפט",
    "לפתוח תיק אחד, להוריד אקסל, לשנות מחיר מכירה בתא הכחול ולראות את הרווח זז",
    "בתיק: הסייגים מופיעים מתחת לרווח, וההיטל מוצג כתקרה ולא כ-0 ₪",
    "לפתוח את המנהרה רק כשמתחילים, ולסגור אותה (Ctrl+C) מיד אחרי",
]


def main() -> int:
    check_code()
    check_processes()
    check_http()
    check_migrations()
    check_auth()
    asyncio.run(check_data())
    check_rendering()
    check_tunnel()

    for level, title, detail in results:
        print(f"  {level}  {title}" + (f"\n       {detail}" if detail else ""))
    print("\n── ביד, כי אין דרך לבדוק את זה מכאן ──")
    for item in MANUAL:
        print(f"  ☐  {item}")

    blocks = sum(1 for lvl, *_ in results if lvl == BLOCK)
    warns = sum(1 for lvl, *_ in results if lvl == WARN)
    print(f"\n{'לא להתחיל' if blocks else 'אפשר להתחיל'} · {blocks} חוסמים · {warns} אזהרות")
    return 2 if blocks else (1 if warns else 0)


if __name__ == "__main__":
    sys.exit(main())
