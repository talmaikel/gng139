"""שלבים 6–9 בשרשרת הזכויות, לפי מדיניות עיריית הרצליה.

הופתעתי פעמיים בקריאת הטקסט, ושתי ההפתעות בכיוון ההפוך להנחה שלי:

  1. מרפסות **מוסיפות** ולא מנכות. "שטחי המרפסות יהיו בנוסף לשטח הנ"ל,
     כאשר ממוצע שטח המרפסות המקסימלי יהיה 12 מ"ר" (סעיף ו').
     הנחתי ששלבים 7–9 מקטינים את השטח הנמכר. שניים מהם מגדילים.

  2. תקרת ה-400% כוללת שטחי שירות. "הזכויות יכללו את כלל השטחים העיקריים
     ואת שטחי השירות, לרבות ממ"דים, מעל הקרקע" — אין להוסיף שטחי שירות בנפרד.
"""

# רצפת ההפרשה לפי אזור רישום. מהמדיניות, סעיף ה'.
FLOOR_300 = {'אלון','ברנר','גן רש"ל','הנדיב','יוחנני','נוף ים','נוף-ים','שז"ר'}
FLOOR_400 = {'בן צבי','ברנדיס','ברנדייס','ויצמן','יצחק נבון','לב טוב','הירוק',
             'בית ספר ירוק (שם זמני)'}

class Undefined(Exception):
    """המדיניות אינה מכסה את המקרה — דורש הכרעה אנושית."""

def allocation(total_after, registration_area):
    """שלב 6 · הפרשה לשב"צ מבונה.
    10% מסך השטחים אחרי ההגדלה. אם התוצאה קטנה מהרצפה — "לא יהיה בה צורך".
    מחזיר (שטח_מופרש, נימוק).
    """
    a = (registration_area or '').strip()
    if a in FLOOR_300:   floor = 300
    elif a in FLOOR_400: floor = 400
    else:
        raise Undefined(f'אזור רישום "{a or "לא ידוע"}" אינו ברשימת הרצפות במדיניות')
    raw = 0.10 * total_after
    if raw < floor:
        return 0.0, f'10% = {raw:,.0f} < רצפת {floor} באזור {a} → לא נדרשת הפרשה'
    return raw, f'10% = {raw:,.0f} ≥ רצפת {floor} באזור {a}'

def balconies(units):
    """שלב 7 · מרפסות. בנוסף לתקרה, עד 12 מ"ר בממוצע ליחידה.
    מחזיר (שטח_מרפסות, נימוק). None כשמספר היחידות אינו ידוע.
    """
    if not units:
        return None, 'מספר יחידות לא ידוע'
    return units * 12.0, f'{units} יח"ד × 12 מ"ר ממוצע מקסימלי'

def unit_mix(existing_units, sellable_main):
    """שלב 8 · תמהיל. מחזיר את טווח היחידות ואת אילוצי התמהיל.

    מדיניות סעיף א': מספר הדירות לא יעלה על הקיים × 2.8–3.18.
    סעיף ב': לפחות 25% דירות קטנות 56–80 מ"ר כולל ממ"ד, ומתוכן עד 10% מיקרו עד 55.
    סעיף ג': 10% דירות נגישות.
    """
    if not existing_units:
        raise Undefined('מספר הדירות הקיים אינו ידוע')
    lo, hi = round(existing_units * 2.8), round(existing_units * 3.18)
    out = dict(units_min=lo, units_max=hi,
               small_min=round(hi * 0.25), micro_max=round(hi * 0.25 * 0.10),
               accessible=round(hi * 0.10))
    if sellable_main:
        out['avg_unit_at_max'] = round(sellable_main / hi, 1)
        out['avg_unit_at_min'] = round(sellable_main / lo, 1)
        # אילוץ: 25% מהדירות חייבות להיות 56–80 מ"ר, ולכן הממוצע נמשך מטה
        out['mix_feasible'] = out['avg_unit_at_max'] >= 56
    return out

def parking(units):
    """שלב 9 · חניה. המדיניות אינה קובעת תקן — היא מפנה לתקן הארצי
    ומוסיפה דרישה לחניות ציבוריות בתוך החניון הפרטי עבור השב"צ.
    """
    raise Undefined('תקן החניה אינו במסמך המדיניות — נדרש תקן ארצי/עירוני')

def run(binding_area, units, existing_units, registration_area):
    """מריץ 6–8 ומחזיר תוצאה עם נימוק לכל שלב. שלב 9 תמיד לא ידוע."""
    res = {'stages': {}, 'flags': []}
    try:
        a, why = allocation(binding_area, registration_area)
        res['allocation'] = a; res['stages']['6'] = why
    except Undefined as e:
        res['allocation'] = None; res['stages']['6'] = f'לא נקבע · {e}'
        res['flags'].append(str(e))
    b, why = balconies(units)
    res['balconies'] = b; res['stages']['7'] = why
    if b is None: res['flags'].append('מרפסות לא חושבו — אין מספר יחידות')
    net_main = binding_area - (res['allocation'] or 0)
    try:
        res['mix'] = unit_mix(existing_units, net_main); res['stages']['8'] = 'חושב'
        if res['mix'].get('mix_feasible') is False:
            res['flags'].append('תמהיל לא ישים — הממוצע נמוך מ-56 מ"ר גם במקסימום יחידות')
    except Undefined as e:
        res['mix'] = None; res['stages']['8'] = f'לא נקבע · {e}'; res['flags'].append(str(e))
    res['stages']['9'] = 'לא נקבע · תקן החניה אינו במדיניות'
    res['flags'].append('חניה לא חושבה')
    res['sellable_main'] = round(net_main)
    res['sellable_with_balconies'] = round(net_main + b) if b else None
    return res
