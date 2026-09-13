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

# צירים ראשיים לפי תקן החניה 2025, סעיף א.1. עליהם "לא יותרו כניסות
# חדשות לרכבים, אלא רק לחלקות כלואות באישור הוועדה המקומית" — כלומר
# פרויקט שכל חזיתו על ציר ראשי עלול שלא לקבל כניסה לחניון.
MAIN_AXES = {'דרך ירושלים', 'העצמאות', 'הרב קוק', 'ארלוזורוב', 'סוקולוב',
             'ויצמן', 'בן גוריון', 'הבריגדה היהודית', 'ז\'בוטינסקי'}


def parking(units, unit_areas=None, in_tama70=None):
    """שלב 9 · חניה, לפי תקן החניה שאושר בוועדת משנה 769 ב-10.09.2025
    ואושרר בישיבה 770 ב-15.10.2025.

    חלופת שקד היא תכנית חדשה, ולכן חל סעיף ב ("תקן חניה לתוכניות חדשות"),
    ולא סעיפי תמ"א 38. בתוך גבולות תמ"א 70 חל ג.1 ומחוצה להם ג.2.

    in_tama70=None אינו ברירת מחדל אלא סירוב: 72% מהניצולים נמצאים בתוך
    תמ"א 70 ו-28% מחוץ לה, וההבדל בתקן הוא 1.0 מול 1.5 ליח"ד. ניחוש כאן
    משנה את מספר החניות ברבע.

    unit_areas: רשימת שטחי הדירות במ"ר. בלעדיה מוחזר התקן הבסיסי בלבד,
    כי ההנחות לדירות קטנות תלויות בתמהיל שעוד לא נקבע.
    """
    if in_tama70 is None:
        raise Undefined('לא ידוע אם החלקה בתוך תמ"א 70 — התקן שונה (1.0 מול 1.5)')
    if not units:
        raise Undefined('מספר יחידות הדיור אינו ידוע')

    if in_tama70:
        # ג.1 — התקן לפי תמ"א 70. הטבלה בפרוטוקול מסמנת ב-X את מדדי
        # נגישות 3 ו-4+5, בהתאם לנימוק שבגוף הפרוטוקול: "בפועל נשענים
        # בשנים הקרובות רק על תנועת אוטובוסים, ולא על קווי מתע"ן".
        # נותר מדד 1+2, שבו מגורים = 1 חניה ליח"ד בשתי הטבעות.
        return {'spaces': units * 1.0, 'per_unit': 1.0, 'guests': None,
                'why': 'תמ"א 70, מדד נגישות 1+2 — 1.0 ליח"ד',
                'caveat': 'מדד הנגישות נקבע במיפוי תמ"א 70 עצמה; כאן נקרא '
                          'מטבלה מסומנת ידנית בפרוטוקול'}

    # ג.2.א — מחוץ לתמ"א 70
    base = 1.5
    if unit_areas is None:
        return {'spaces': units * base, 'per_unit': base, 'guests': None,
                'why': 'מחוץ לתמ"א 70 — 1.5 ליח"ד, ללא הנחות לדירות קטנות',
                'caveat': 'תמהיל הדירות לא נמסר; דירות עד 65 מ"ר מקבלות תקן נמוך יותר'}

    spaces = 0.0
    small = 0
    for a in unit_areas:
        if a <= 30:
            spaces += 0.0; small += 1      # תקן 0, אך נדרש מרתף עם חניות נגישות
        elif a <= 65:
            spaces += 1.0; small += 1
        else:
            spaces += base
    # חניות אורחים: "בתב\"עות שבהם תקן החניה 1:1-0, ידרשו 20% ממספר יח"ד",
    # ניתן להקטין ל-10% באישור הוועדה. חל על החלק שתקנו 1 ומטה.
    guests = round(small * 0.20, 1)
    return {'spaces': round(spaces, 1), 'per_unit': round(spaces / units, 2),
            'guests': guests,
            'why': f'מחוץ לתמ"א 70 · {units - small} יח"ד × 1.5 + {small} קטנות · '
                   f'אורחים 20% מ-{small} (ניתן להקטין ל-10%)',
            'caveat': 'דירות עד 30 מ"ר בתקן 0 מחייבות קומת מרתף עם חניות נגישות '
                      'בשיעור 10% מהן'}


def main_axis_flag(street_names):
    """האם החלקה פונה לציר ראשי — ואז כניסה חדשה לרכבים אינה מובטחת."""
    hits = [n for n in street_names if any(ax in n for ax in MAIN_AXES)]
    if not hits:
        return None
    return ('חזית על ציר ראשי (' + ', '.join(sorted(set(hits))) + ') — '
            'תקן החניה 2025 ס\'א.2: לא יותרו כניסות חדשות לרכבים, '
            'למעט חלקות כלואות באישור הוועדה')


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
