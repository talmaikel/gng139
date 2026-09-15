"""רוחב הרחוב של האלגוריתם מול כל חזית שנמדדה ביד.

  python validation/evaluate_widths.py

מקורות האמת:
  street_width.csv + d1_followup.json   — D1, שני מודדים (כאן החציון של טל, והחזיתות השניות מההערות)
  narrow_streets.json, wide_streets.json — מדידות אימות בפורמט המשותף (frontages: parcel, street, a/b/c, kind)

חזית שהמודד סימן כלא-רחוב (שביל, דרך שירות, חניון) נספרת בנפרד: שם האלגוריתם אינו
אמור לדייק, אלא לא להציג אותה כרחוב. מחזיר קוד 1 אם רחוב אמיתי יצא מחוץ ל-±1 מ׳.
"""
import json, statistics, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from build_frontages import V2

TOLERANCE_M = 1.0

# D1: החזית שנמדדה, בשם שבו OSM מכיר את הרחוב (תת-מחרוזת), וחציון שלוש הנקודות.
D1 = [
    ("6529/43", "יהודה הלוי", 8.2), ("6538/476", "מזא", 9.7), ("6531/160", "הגליל", 8.92),
    ("6537/5", "יגאל אלון", 10.5), ("6529/63", "אלי כהן", 10.0), ("6530/214", "טשרניחובסקי", 10.0),
    ("6530/214", "הראשונים", 10.8), ("6536/194", "פלמ", 10.2), ("6536/841", "עגנון", 11.3),
    ("6530/191", "הנביאים", 11.5), ("6530/191", "מלכי יהודה", 11.3), ("6546/498", "עקיבא", 14.98),
    ("6533/283", "רופין", 9.9), ("6536/550", "ברוך", 16.7), ("6538/553", "ארלוזורוב", 18.3),
    ("6538/553", "שווידלסון", 10.4),
]
D1_NOT_STREET = [("7291/146", "הצנחנים", 8.0, "path")]   # בניין "רכבת" ששביל של 2.3 מ׳ מפריד בינו לשכניו


def measured(file):
    p = HERE / file
    if not p.exists():
        return [], []
    streets, other = [], []
    for f in json.load(open(p, encoding="utf-8"))["frontages"]:
        pts = [float(f[k]) for k in "abc" if f.get(k) not in (None, "")]
        if not pts:
            continue
        row = (f["parcel"], f["street"], round(statistics.median(pts), 2))
        # סוג ריק = המודד לא סימן; בהערות של wide_streets אלה רחובות (מרכז מסחרי, רחוב עם חניות).
        (streets if f.get("kind") in ("street", "", None) else other).append(row + (f.get("kind") or "?",))
    return [r[:3] for r in streets], other


def main():
    truth, not_street = list(D1), list(D1_NOT_STREET)
    for file in ("narrow_streets.json", "wide_streets.json"):
        s, o = measured(file)
        truth += s; not_street += o

    v = V2()
    def closest(key, street, t):
        # החזית הצרה ביותר לאותו רחוב — מה שהכלל משתמש בו. לא הקרובה לאמת: זה היה מציץ בתשובה.
        s = (v.stree, v.streets, v.tags, v.names)
        from street_frontage import classify_run
        cand = [(r["width"], *classify_run(r, *s)) for r in v.runs(key)]
        named = [c for c in cand if street.replace('"', '') in (c[2] or "").replace('"', '')]
        return min(named, key=lambda c: c[0]) if named else None

    bad, errs, band_ok = [], [], 0
    print(f"{'חלקה':9} {'רחוב':14} {'ביד':>6} {'אלגוריתם':>9}")
    for key, street, t in truth:
        c = closest(key, street, t)
        w = c[0] if c else None
        ok = w is not None and abs(w - t) <= TOLERANCE_M
        if w is not None: errs.append(abs(w - t))
        if w is not None and (w > 12) == (t > 12): band_ok += 1
        if not ok: bad.append((key, street, t, w))
        print(f"{key:9} {street:14} {t:6} {str(w):>9}{'' if ok else '  ✗'}")
    print(f"\nרחובות: {len(truth) - len(bad)}/{len(truth)} בתוך ±{TOLERANCE_M:g} מ׳ · "
          f"חציון שגיאה {statistics.median(errs):.2f} מ׳ · אותו צד של 12 מ׳: {band_ok}/{len(truth)}")

    print("\nלא-רחובות (לפי המודד) — מה האלגוריתם אמר:")
    for key, street, t, kind in not_street:
        c = closest(key, street, t)
        print(f"  {key:9} {street:14} {kind:8} ביד {t:6} · אלגוריתם {c[0] if c else '—'} ({c[1] if c else '—'})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
