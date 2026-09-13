#!/usr/bin/env python3
"""בדיקת הגשר. הנקודה: שדה בלי מקור או בלי מיקום חייב ליפול ב-usable().

זו התקלה שקשה לראות — היא אינה זורקת שגיאה, היא מחזירה תוצאות ריקות.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.bridge import to_fields
from app.rules import usable, evidence

REQUIRED = ('parcel_area', 'units', 'floors', 'renewal_policy_category')
fails = []


def check(ok, msg):
    print(f'  [{"PASS" if ok else "FAIL"}] {msg}')
    if not ok:
        fails.append(msg)


print('\n  הגשר · שדות נדרשים עוברים usable()')
f = to_fields('6424/144')                     # הר מירון 1
check(f is not None, 'חלקה מוכרת מחזירה fields')
for k in REQUIRED:
    check(usable(f[k]), f'{k} · usable')
check(f['units']['value'] == 32, 'units = 32 כמו בשכבה א׳')
check(f['floors']['source']['url'].startswith('https://'), 'למקור יש כתובת')
check(f['parcel_area']['location'] is not None, 'למקור יש מיקום')

print('\n  שדה בלי מקור אינו עובר')
check(not usable(evidence(5)), 'ערך בלי מקור ומיקום נופל')
check(not usable(evidence(5, source={'url': 'https://x'}, certainty='official')),
      'מקור בלי retrieved_at נופל')
check(not usable(f['planning_lot']), 'planning_lot ללא מקור — missing')

print('\n  קטגוריות המדיניות כלשון הר/2323')
from app.bridge import CATEGORY
check(all('מגרשית' in v for v in CATEGORY.values()),
      'שתי הקטגוריות "מגרשית" — "עירונית" אינו מופיע בתכנית')

print('\n  חלקה לא מוכרת')
check(to_fields('9999/1') is None, 'מפתח לא קיים מחזיר None')

print(f'\n  {"הכל עבר" if not fails else str(len(fails)) + " נכשלו"}\n')
sys.exit(1 if fails else 0)
