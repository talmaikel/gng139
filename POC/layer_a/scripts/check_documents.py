#!/usr/bin/env python3
"""בדיקה תקופתית: האם מסמך מדיניות השתנה, נעלם, או נוסף.

הרקע — ‏13.09.2026: שני ממצאים גדולים התגלו במקרה. כלל "מעל 15 מ׳" היה מונח
בתכנית האסטרטגית שכבר החזקנו, ותקן החניה הוחלף בספטמבר 2025 בלי שידענו.
מסמך שלישי, הנוהל ממרץ 2025, עדיין מפורסם עם תנאי סף שפג — ומי שיקרא אותו
היום יפסול את כל המלאי. שלושתם היו נתפסים על ידי הבדיקה הזו.

מה נבדק:
  1. כל מסמך רשום — האם התוכן השתנה, והאם הוא עדיין קיים.
  2. דפי המפתח — האם הופיע קישור PDF שאיננו מכירים, או נעלם אחד שכן.

השני חשוב לא פחות מהראשון: מסמך אפריל 2026 לא "השתנה", הוא **נוסף**.

שתי רמות התראה:
  שינוי תוכן   — הטקסט שונה. זו התראה אמיתית, יש לקרוא מחדש.
  פרסום מחדש   — הבייטים שונים והטקסט זהה (PDF נשמר מחדש). לידיעה בלבד.

הערה על ה-UA: robots.txt של האתר מתיר הכל למעט תיקיית טפסים, אבל ה-WAF
מחזיר 403 ל-User-Agent אוטומטי. הצהרה על UA של דפדפן היא התאמת תאימות
לגישה שהאתר עצמו מתיר, לא עקיפה של בקרת גישה.

שימוש:
    python check_documents.py              בדיקה; יוצא 1 אם משהו השתנה
    python check_documents.py --update     קובע את המצב הנוכחי כבסיס
"""
import hashlib
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date

from _paths import DATA

MANIFEST = DATA / "documents.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
TIMEOUT = 90


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def pdf_text(blob):
    """טקסט המסמך — זה מה שקובע אם התוכן השתנה, לא הבייטים."""
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(blob))
        return "\n".join((p.extract_text() or "") for p in r.pages)
    except Exception:
        return None


def digest(b):
    return hashlib.sha256(b).hexdigest()[:16]


def norm(url):
    """השוואת כתובות: בדף הן עברית גולמית ובמרשם מקודדות באחוזים.
    בלי הנרמול הזה כל מסמך רשום נראה 'חדש' בכל בדיקה."""
    return urllib.parse.unquote(url).strip()


def pdf_links(html, base):
    out = {}
    for m in re.finditer(r'href="([^"]+\.pdf)"', html, re.I):
        u = urllib.parse.urljoin(base, m.group(1))
        out[u] = urllib.parse.unquote(u.rsplit("/", 1)[-1])
    return out


def check(update=False):
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    alerts, notes = [], []

    print(f"בדיקת מסמכים · {date.today().isoformat()}\n")

    print("מסמכים רשומים")
    for d in man["documents"]:
        try:
            blob = fetch(d["url"])
        except Exception as e:
            alerts.append(f'{d["title"]} — לא נגיש ({e.__class__.__name__}). '
                          f'ייתכן שהוסר או הוחלף.')
            print(f'  ✗ {d["title"]}  — לא נגיש')
            continue

        b_hash = digest(blob)
        text = pdf_text(blob)
        t_hash = digest(text.encode()) if text is not None else None

        if update:
            d["sha_bytes"], d["sha_text"] = b_hash, t_hash
            d["checked"] = date.today().isoformat()
            print(f'  · {d["title"]}  נרשם')
            continue

        if t_hash and d.get("sha_text") and t_hash != d["sha_text"]:
            alerts.append(f'{d["title"]} — **התוכן השתנה**. יש לקרוא מחדש '
                          f'ולבדוק מה נגזר ממנו: {d.get("used_for", "—")}')
            print(f'  ⚠ {d["title"]}  — התוכן השתנה')
        elif b_hash != d.get("sha_bytes"):
            notes.append(f'{d["title"]} — פורסם מחדש, הטקסט זהה.')
            print(f'  ~ {d["title"]}  — פורסם מחדש, טקסט זהה')
        else:
            print(f'  ✓ {d["title"]}')

    print("\nדפי מפתח — מסמכים חדשים או שנעלמו")
    known = {norm(d["url"]) for d in man["documents"]}
    ignored = {norm(u) for u in man.get("ignored", [])}
    seen = {norm(u) for u in man.get("seen_links", [])}

    # אוספים קודם מכל הדפים, ורק אז משווים. בדיקה לכל דף בנפרד מדווחת
    # שמסמך "נעלם" רק משום שהוא חי בדף אחר.
    fnorm = {}
    ok = True
    for page in man["index_pages"]:
        try:
            html = fetch(page).decode("utf-8", "replace")
        except Exception as e:
            alerts.append(f"דף {page} אינו נגיש ({e.__class__.__name__})")
            print(f"  ✗ {page}")
            ok = False
            continue
        found = pdf_links(html, page)
        print(f"  {page}  — {len(found)} קישורי PDF")
        for u in found:
            fnorm[norm(u)] = found[u]

    new = [n for n in fnorm if n not in known and n not in ignored and n not in seen]
    for n in sorted(new):
        alerts.append(f"מסמך חדש שלא מוכר: {fnorm[n]}\n      {n}")
        print(f"    + חדש: {fnorm[n]}")
    if ok:
        gone = [n for n in known if n not in fnorm]
        for n in sorted(gone):
            alerts.append(f"מסמך רשום נעלם מדפי המפתח: {n}")
            print(f"    − נעלם: {n}")
    if update:
        man["seen_links"] = sorted(seen | set(fnorm))

    if update:
        man["baseline_set"] = date.today().isoformat()
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(f"\nהבסיס נקבע ל-{man['baseline_set']}.")
        return 0

    print()
    if notes:
        print("לידיעה:")
        for n in notes:
            print(f"  · {n}")
        print()
    if alerts:
        print(f"התראות ({len(alerts)}):")
        for a in alerts:
            print(f"  ⚠ {a}")
        print("\nאחרי הטיפול: python check_documents.py --update")
        return 1
    print("אין שינוי.")
    return 0


if __name__ == "__main__":
    sys.exit(check(update="--update" in sys.argv))
