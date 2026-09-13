"""טסט רגרסיה לשכבה א'. חייב לרוץ אחרי כל רענון של המקורות.
כל מקרה כאן אומת ידנית מול מקור ראשוני — אל תשנה ציפייה בלי לאמת מחדש.
יוצא עם 1 בכשל, כדי שאפשר יהיה לחבר אותו ל-CI.
"""
import json, os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from _paths import DATA

# (חלקה, צפוי לעבור, מה זה בודק, מקור האמת)
GEOMETRIC = [
    ('7291/145', True,  'הצנחנים 191 · צהוב 92.8%',        'מפרט 19830050 · "2 קומות 12 דירות"'),
    ('7291/146', True,  'הצנחנים 15 · צהוב 100%',           'מפת הר/2323 עמ׳ 7'),
    ('7291/149', True,  'בר-כוכבא 105 · צהוב 100%',         'מפרט 19830049 · "בנין 8 דירות"'),
    ('6424/144', True,  'הר מירון 1 · כשיר גיאומטרית',      'נפסל רק בשכבה ב׳ — היתר חיזוק 2024'),
    ('6529/100', False, 'השושנים 4 · מתחם עירוני להעצמה',   'מפה RGB 181,53,53 ב-62.8%'),
]
APARTMENTS = [
    ('6424/118', False, 'הגלבוע 14 · בית פרטי, num_aprt=1',  'טופס 1 · בקשה 19961016 · קיים 107.86'),
    ('7291/149', True,  'בר-כוכבא 105 · 8 דירות',            'num_aprt סוכם 8 = המפרט'),
    ('7291/145', True,  'הצנחנים 191 · 16 דירות ב-4 כניסות', 'המפרט מתאר בניין אחד, הסכום את החלקה'),
]

def load(name):
    p = DATA / name
    if not p.exists():
        return None
    return {r['key'] for r in json.load(open(p, encoding='utf-8'))}

def run(cases, keys, title):
    print(f"\n  {title}")
    bad = 0
    for key, want, what, src in cases:
        got = key in keys
        ok = got == want
        bad += not ok
        mark = 'PASS' if ok else '*** FAIL ***'
        print(f"  [{mark}] {key:<11} צפוי {'לעבור' if want else 'ליפול':<6} · "
              f"בפועל {'עבר' if got else 'נפל':<4} — {what}")
        if not ok:
            print(f"           מקור האמת: {src}")
    return bad

def main():
    geo = load('survivors.json')
    apt = load('survivors_apt.json')
    if geo is None:
        sys.exit("חסר data/survivors.json — הרץ scripts/build_layer_a.py")
    print("טסט רגרסיה · שכבה א׳")
    bad = run(GEOMETRIC, geo, f"שערים גיאומטריים ({len(geo):,} שורדים)")
    if apt is None:
        print("\n  [דילוג] survivors_apt.json חסר — שער ≥4 דירות לא נבדק")
    else:
        bad += run(APARTMENTS, apt, f"שער ≥4 יחידות דיור ({len(apt):,} שורדים)")
    print(f"\n  {'הכל עבר' if not bad else f'{bad} כשלים'}")
    return 1 if bad else 0

if __name__ == '__main__':
    sys.exit(main())
