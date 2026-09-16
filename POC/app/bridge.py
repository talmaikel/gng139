"""הגשר: פלט layer_a → מבנה ה-fields של ה-POC.

‏layer_a מחשב מראש 700 מועמדים כשירים לכל העיר. ה-POC מצפה ל-dict של
שדות, כל אחד עטוף ב-`rules.evidence()`, ו-`rules.usable()` מחליטה אם שדה
נחשב ראיה. **זו הנקודה שבה שני הצינורות נפגשים.**

המלכודת שמעצבת את כל הקובץ: `usable()` דורשת ארבעה תנאים במצטבר —
certainty מתוך רשימה מותרת, `source.url`, `source.retrieved_at` בתוך
SOURCE_MAX_AGE_DAYS, ו-`location` שאינו None. שדה שחסר לו אחד מהם חוזר
`unknown` **וחוסם מסירה בשקט**, בלי הודעת שגיאה. לכן כל שדה כאן נבנה דרך
`_ev()` שמחייב מקור ומיקום, ואין דרך לייצר שדה "עובר" בלי אחד מהם.

‏`retrieved_at` מגיע מ-`data/source_fetched.json` — זמן השליפה **האמיתי**
של שכבת המקור. לא `now()`. ‏now() היה עובר ולידציה ומשקר.

מה שהקובץ הזה במכוון אינו עושה: אינו ממציא ערך חסר. שדה שאין לו מקור
יוצא `missing`, וה-`report()` מונה אותם — זו הרשימה שמשימה A3 דורשת.
"""
import json
from pathlib import Path

from .rules import evidence

ROOT = Path(__file__).resolve().parents[1]
LAYER_A = ROOT / 'layer_a' / 'data'

_cache = {}


def _load(name):
    if name not in _cache:
        _cache[name] = json.loads((LAYER_A / name).read_text(encoding='utf-8'))
    return _cache[name]


def _sources():
    return _load('source_fetched.json')


def _ev(value, source_id, location, certainty='official', method=None):
    """ראיה עם מקור ומיקום. חסר אחד מהם — השדה יוצא missing ולא 'כאילו עבר'."""
    if value is None:
        return evidence(None)
    src = _sources().get(source_id)
    if not src or not location:
        return evidence(None)
    return evidence(value,
                    source={'url': src['url'], 'retrieved_at': src['retrieved_at'],
                            'label': src['label']},
                    certainty=certainty, location=location, method=method)


# קטגוריות מפת המדיניות, כלשונן בעמ׳ 8 של הר/2323.
# שים לב: rules.evaluate() מצפה ל'התחדשות עירונית מוטת מגורים נמוכה'
# בעוד שהתכנית כותבת 'מגרשית'. ראה report() — זו אי-התאמה אמיתית.
CATEGORY = {
    '9':   'התחדשות מגרשית מוטת מגורים',
    '5.5': 'התחדשות מגרשית מוטת מגורים נמוכה',
}
CEILING = {'9': 9.0, '5.5': 5.5}


def _archive(key):
    """בקשות ההיתר לחלקה, אם התיק שלה נסרק. 84 תיקים מול 700 מועמדים."""
    tiks = _load('parcel_tiks.json').get(key) or []
    facts = {f['tik']: f for f in _load('archive_facts.json')}
    out = []
    for t in tiks:
        if t in facts:
            out += facts[t].get('requests', [])
    return out or None


def to_fields(key):
    """מחזיר את מבנה ה-fields של ה-POC לחלקה אחת. key בצורת 'גוש/חלקה'."""
    surv = {x['key']: x for x in _load('survivors_apt.json')}.get(key)
    if not surv:
        return None
    front = {x['key']: x for x in _load('frontages.json')}.get(key, {})
    gush, helka = key.split('/')
    at = f'גוש {gush} חלקה {helka}'
    cat = str(surv.get('cat'))

    f = {}

    # ── שדות שהשערים הקיימים ב-evaluate() בודקים ──
    f['parcel_area'] = _ev(surv.get('lot'), 'govmap_parcels', at)
    f['units'] = _ev(surv.get('apt'), 'agol_addresses',
                     f'{at} · {surv.get("entrances")} כניסות',
                     method='סכום num_aprt על נקודות הכתובת בתוך החלקה')
    f['floors'] = _ev(surv.get('floors'), 'agol_buildings', at,
                      method='מקסימום Num_floors על המבנים בחלקה')
    f['renewal_policy_category'] = _ev(
        CATEGORY.get(cat), 'strategic_plan', f'{at} · עמ׳ 8 במפת המדיניות',
        certainty='derived',
        method='דגימת דיסק 15 מ׳ במפה שגאו-רפרנסה, התאמת צבע קרובה, הכרעת רוב')

    # מסלול מגרשים: חלקה אחת. מספר המבנים נספר בשכבה העירונית.
    f['scope_parcels'] = _ev(1, 'govmap_parcels', at, certainty='derived',
                             method='סריקת חלקה בודדת; צמדים אינם בהיקף הבטא')
    # survivors_apt.json has no building count; build_layer_a.py writes it to survivors.json as nb.
    nb = {x['key']: x for x in _load('survivors.json')}.get(key, {}).get('nb')
    f['scope_buildings'] = _ev(nb, 'agol_buildings', at,
                               method='מבנים מהשכבה העירונית בתוך החלקה')

    # ── שערי הארכיון. 84 תיקים מול 700 — היעדר נתון אינו "עבר" ──
    reqs = _archive(key)
    if reqs:
        years = [int(str(r['req'])[:4]) for r in reqs if str(r.get('req', ''))[:4].isdigit()]
        loc = f'{at} · {len(reqs)} בקשות בתיק'
        if years:
            f['permit_date'] = _ev(f'{min(years)}-01-01', 'govmap_parcels', loc,
                                   certainty='derived',
                                   method='שנת הבקשה המוקדמת ביותר בתיק הבניין')
        import re
        pat = re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')
        hit = any(pat.search(r.get('action') or '') and (r.get('permit_date') or '').strip()
                  for r in reqs)
        f['strengthened'] = _ev(hit, 'govmap_parcels', loc, certainty='derived')

    # ── מה שאין לו מקור. במפורש, ולא בשקט ──
    for k in ('residential_zoning', 'residential_share', 'engineer_opinion',
              'planning_lot', 'planning_basis', 'overriding_plans_checked'):
        f.setdefault(k, evidence(None))
    for k in ('permit_date', 'strengthened'):
        f.setdefault(k, evidence(None))

    # ── שדות שאינם שערים אבל התיק מציג ──
    f['street_width'] = _ev(front.get('width'), 'govmap_parcels',
                            f'{at} · {front.get("why", "")}'[:120],
                            certainty='derived',
                            method='פער קדסטרלי, החזית הצרה קובעת; אמין עד 15 מ׳')
    f['category_ceiling'] = _ev(CEILING.get(cat), 'strategic_plan',
                                f'{at} · עמ׳ 8', certainty='derived')
    return f


def report(keys=None):
    """אילו שדות עוברים usable() ואילו לא — הפלט שמשימה A3 דורשת."""
    from .rules import usable
    from collections import Counter
    keys = keys or [x['key'] for x in _load('survivors_apt.json')]
    ok, miss = Counter(), Counter()
    for k in keys:
        fields = to_fields(k) or {}
        for name, fld in fields.items():
            (ok if usable(fld) else miss)[name] += 1
    return {'n': len(keys), 'usable': dict(ok), 'not_usable': dict(miss)}
