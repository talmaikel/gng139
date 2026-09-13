"""דירוג מועמדים. ארבעה עקרונות, וכולם נובעים ממה שנמדד ולא מהעדפה.

1. דירוג לפי חסם תחתון, לא לפי אומדן נקודתי.
   מקדם ההמרה k כויל על נקודת אמת אחת, ולכן אינו ראוי לדירוג נקודתי.
   הערה חשובה: כשתקרת 400% חוסמת, value = 4·ברוטו·k — ו-k הוא גורם משותף
   שאינו משנה את הסדר. הוא קובע *איזה* חסם נכנס לפעולה, לא מי ראשון.
   לכן משתמשים בטווח k ומסמנים מועמד שהחסם שלו מתהפך בתוך הטווח.

2. עדיפות למועמד שתקרת ה-400% חוסמת אצלו.
   נמדד: 400% חוסם ברוב המקרים, המעטפת בחלק. המעטפת היא הצד הלא ודאי —
   קו הבניין מגיע מתב"ע שאינה זמינה, והפרש 3 מ' מול 4 מ' מזיז את התוצאה
   בעשרות אחוזים. מועמד שה-400% חוסם אצלו נושא מספר יציב.

3. מועמד "תפוס" יוצא לגמרי.
   בקשת תמ"א 38 שלא הבשילה להיתר פירושה שיזם אחר כבר עובד מול הדיירים.
   משפטית הבניין כשיר; מעשית הוא לא זמין. שער קשיח, לא הורדה בדירוג.

4. מועמד שדירוגו נשען על קלט לא מדוד מסומן במפורש ולא מוצג כוודאי.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from street_rule import floors_for_parcel, Undefined

K_NOMINAL = 0.669          # כויל מול היתר 19780028
K_RANGE   = (0.60, 0.74)   # הנחה, לא מדידה — n=1 אינו מאפשר רווח סמך אמיתי

def existing_area(gross, k): return gross * k

def envelope(parcel_geom_rect, floors, side=3.5, front=5.0, rear=6.0):
    """מעטפת גסה. side/front/rear אינם מדודים — קו הבניין מגיע מתב"ע שאין לנו."""
    if floors is None: return None
    a, b = parcel_geom_rect
    return max(a - 2*side, 0) * max(b - front - rear, 0) * floors

def occupied(requests):
    """תמ"א 38 / חיזוק שהוגש ולא הופק לו היתר → יזם אחר כבר בתמונה."""
    import re
    pat = re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')
    for r in requests or []:
        if pat.search(r.get('action') or '') and not (r.get('permit_date') or '').strip():
            return True, r.get('req') or '(ללא מספר)'
    return False, None

def strengthened(requests):
    """חיזוק שהופק לו היתר → פסול לפי 70א(2)."""
    import re
    pat = re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')
    for r in requests or []:
        if pat.search(r.get('action') or '') and (r.get('permit_date') or '').strip():
            return True, r.get('req')
    return False, None

def score(c):
    """c: dict עם gross, rect, frontages, map_cap, requests (אופציונלי).
    מחזיר dict עם value_lo, value_hi, bound_by, stable, flags, excluded.
    """
    out = dict(key=c['key'], flags=[], excluded=None)
    reqs = c.get('requests')

    if reqs is not None:
        hit, rq = strengthened(reqs)
        if hit:
            out['excluded'] = f'חוזק בהיתר · בקשה {rq}'; return out
        hit, rq = occupied(reqs)
        if hit:
            out['excluded'] = f'תפוס · בקשת חיזוק {rq} ללא היתר'; return out
    else:
        out['flags'].append('היסטוריית היתרים לא נבדקה')

    # גובה — רק אם רוחב הרחוב ידוע והטבלה נותנת מספר
    floors, why = (None, 'רוחב רחוב לא נמדד')
    if c.get('frontages'):
        floors, why = floors_for_parcel(c['frontages'], c['map_cap'])
    out['floors'], out['floors_why'] = floors, why
    if floors is None:
        out['flags'].append(f'גובה לא נקבע · {why}')

    env = envelope(c['rect'], floors) if c.get('rect') else None
    if env is None:
        out['flags'].append('מעטפת לא חושבה — לא ניתן לדעת איזה חסם פועל')

    vals = {}
    for lbl, k in (('lo', K_RANGE[0]), ('hi', K_RANGE[1])):
        cap = 4 * existing_area(c['gross'], k)
        if env is None:
            # המעטפת לא חושבה — 400% הוא החסם היחיד שניתן לחשב, ולכן חסם עליון בלבד
            vals[lbl] = (cap, 'לא ידוע')
        else:
            vals[lbl] = (cap, '400%') if cap <= env else (env, 'מעטפת')
    out['value_lo'], bl = vals['lo']
    out['value_hi'], bh = vals['hi']
    out['bound_by'] = bl if bl == bh else 'מתהפך'
    out['stable']   = bl == bh and bl != 'לא ידוע'
    out['is_upper_bound'] = (bl == 'לא ידוע')
    if not out['stable']:
        out['flags'].append('החסם מתהפך בתוך טווח k — הערך אינו יציב')
    if env is not None and out['bound_by'] == 'מעטפת':
        out['flags'].append('מעטפת חוסמת — נשען על מרווחים שלא נמדדו')
    return out

def rank(cands):
    """מסלק מודרים, ואז ממיין: ערך שמרני ↓, יציבות ↓, מספר סימונים ↑."""
    live = []
    for c in cands:
        s = score(c)
        if s['excluded']: continue
        live.append({**c, **s})
    live.sort(key=lambda r: (-r['value_lo'], not r['stable'],
                             r['bound_by'] != '400%', len(r['flags'])))
    return live
