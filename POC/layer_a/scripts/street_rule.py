"""גזירת מספר הקומות מרוחב הרחוב — לפי מדיניות עיריית הרצליה, סעיף 5
"גובה אל מול חתך הרחוב" (עמ' 8).

הכלל נגזר מהטקסט ולא מניחוש:

  "בהרצליה קיימת שונות בין הרחובות, המחייבת התייחסות שונה לגובה המבנים ביחס
   לרוחב הרחובות, זאת מתוך מטרה להימנע ממצבים בהם הרחובות מועמסים על ידי בינוי
   אשר גורם לתחושת צפיפות יתר. מטרת הנסיגה בחזיתות הפונות לרחוב הינה לצמצם בעיה זו"

הכלל מנוסח **פר-חזית**. לכן במגרש פינה עם שתי חזיתות, החזית הצרה קובעת את הגובה —
בניין גבוה מעמיס את הרחוב הצר בלי קשר לרחוב רחב בצד השני. MIN, לא MAX.

מאושש בהערה 3 לטבלה: "בצמתים ניתן לבחון תוספת קומה מעבר לאמור בטבלה בכפוף
לנימוקים לועדה המקומית" — חריג לפי שיקול דעת, שהגיוני רק אם הבסיס בפינה מגביל.
"""

# (גבול עליון בלעדי, קומות ללא נסיגה, מקסימום קומות)
TABLE = [
    ( 8.0, None, None),   # "עד 8 מ' כולל — לא תותר תוספת"
    ( 9.0, None, None),   # חור בטבלה: 8–9 מ' אינו מוגדר במדיניות
    (10.0,    6,    7),
    (12.0,    6,    8),
    (15.0,    7,    9),
]

class Undefined(Exception):
    """רוחב שהמדיניות אינה נותנת לו מספר — צריך הכרעה אנושית."""


# תחום אי-הוודאות של מדידת הפער הקדסטרלי, במטרים לכל צד.
#
# זו **הנחה, לא מדידה.** נכון ל-13.09.2026 אין נקודת אמת חיצונית: פוליגוני
# הדרך של XPlan נבדקו מול 209 חלקות ונתנו חציון הפרש של 22 מ׳ — הם רצועות
# תכנון, לא זכות הדרך הקיימת. עד שיימדדו חלקות ידנית ב-GovMap (אותה כמות
# בדיוק, ולכן אימות תקף של החישוב) הערך הזה נשאר הנחה שמרנית.
#
# למה זה חשוב: 45% מהחלקות המדודות יושבות בטווח מטר מסף מדיניות כלשהו,
# ו-73 מהן (11%) בטווח מטר מקו ה-8–9 מ׳ — הקו שמפריד בין פרויקט ללא-פרויקט.
TOLERANCE_M = 1.0

# מעל הרוחב הזה המדידה אינה אמינה — ואין צורך שתהיה.
#
# נבדק ב-13.09 מול מיקום ציר הרחוב ב-OSM: אם החלקה יושבת בקצה זכות הדרך,
# הרוחב אמור להיות ~פי-2 המרחק לציר. עד 15 מ׳ העודף קבוע (+3.2 עד +3.6 מ׳,
# בדיוק מה שמצופה מאי-סימטריה של מדרכות). מעל 15 הוא מתפוצץ: +8.0 בטווח
# 15–20, +11.9 בטווח 20–25, +19.1 מעל 25. הקרן בורחת מעבר לרחוב — לחניון,
# לשטח פתוח, לחצר. ראיה שנייה: רחובות primary יוצאים בחציון 16.5 מ׳ ורחובות
# residential 16.2 — מדידה שאינה מבחינה בין עורק לרחוב מגורים אינה מודדת רחוב.
#
# זה לא פוגע בשרשרת: מעל 15 מ׳ המדיניות ממילא קובעת "בחינה נקודתית" ולא
# מספר, ו-floors_for_frontage כבר מרימה שם Undefined. מה שאסור הוא להציג
# את המספר עצמו כאילו נמדד.
RELIABLE_MAX_M = 15.0


def display_width(width_m):
    """הרוחב כפי שמותר לכתוב אותו בתיק."""
    if width_m is None:
        return "לא נמדד"
    if width_m > RELIABLE_MAX_M:
        return f"מעל {RELIABLE_MAX_M:.0f} מ׳ (הערך המדויק אינו אמין)"
    return f"{width_m:.1f} מ׳"

def floors_for_frontage(width_m):
    """מחזיר (ללא_נסיגה, מקסימום). None,None = לא תותר תוספת."""
    if width_m is None:
        raise Undefined("רוחב לא נמדד")
    if width_m <= 8.0:
        return (None, None)
    if width_m < 9.0:
        raise Undefined("8–9 מ' — טווח שאינו מוגדר בטבלת המדיניות")
    for upper, plain, mx in TABLE[2:]:
        if width_m <= upper:
            return (plain, mx)
    # "מעל 15 — נקודתית, יבחן בהתאם למדיניות להתחדשות מרכז העיר ותמ"א 70"
    raise Undefined("מעל 15 מ' — המדיניות קובעת בחינה נקודתית, לא מספר")

def floors_band(width_m, tol=TOLERANCE_M, step=0.1):
    """מה המדיניות אומרת על כל התחום [w-tol, w+tol], לא רק על w.

    סורק את התחום בצעדים קטנים — כך שגם פער לא-מוגדר שנופל *בתוך* התחום
    ולא על קצותיו נתפס. מחזיר dict:
      low / high   — טווח הקומות מהחלקים שהמדיניות כן נותנת להם מספר
      certain      — כל התחום נותן אותה תשובה
      none_share   — חלק התחום שבו "לא תותר תוספת"
      undef_share  — חלק התחום שהמדיניות לא נותנת לו מספר
      undef_why    — הנימוק הראשון שהתקבל, לציטוט בתיק
    """
    n = max(int(2 * tol / step), 1)
    lo_w = width_m - tol
    numbers, none_hits, undef_hits, undef_why = [], 0, 0, None
    for i in range(n + 1):
        w = lo_w + i * step
        if w <= 0:
            continue
        try:
            _, mx = floors_for_frontage(w)
        except Undefined as e:
            undef_hits += 1
            undef_why = undef_why or str(e)
            continue
        if mx is None:
            none_hits += 1
        else:
            numbers.append(mx)
    total = n + 1
    return {
        "low": min(numbers) if numbers else None,
        "high": max(numbers) if numbers else None,
        "certain": len(numbers) == total and min(numbers) == max(numbers),
        "none_share": none_hits / total,
        "undef_share": undef_hits / total,
        "undef_why": undef_why,
    }


def floors_for_parcel(frontage_widths, map_cap):
    """map_cap: 9 לצהוב, 5.5 לצהוב בהיר.
    מחזיר (מקסימום_קומות, נימוק). None = לא כשיר / לא ניתן לקבוע.
    """
    if not frontage_widths:
        return None, "אין חזית רחוב מזוהה"
    results, notes = [], []
    for w in frontage_widths:
        try:
            _, mx = floors_for_frontage(w)
        except Undefined as e:
            return None, f"{w} מ': {e}"
        if mx is None:
            return None, f"חזית {w} מ' — עד 8 מ' כולל, לא תותרת תוספת"
        results.append(mx); notes.append(f"{w}→{mx}")
    street = min(results)                      # החזית הצרה קובעת
    final = min(street, map_cap)
    why = f"חזיתות {', '.join(notes)} · צרה קובעת {street} · מפה {map_cap} → {final}"
    return final, why


def parcel_report(frontage_widths, map_cap, tol=TOLERANCE_M):
    """מה שנכנס לתיק: מספר ודאי, או טווח עם דגל — אף פעם לא מספר מדומה.

    כשחלק מהתחום אינו מוגדר במדיניות, לא נמחק כל התוצאה: מדווח את הטווח
    שכן ידוע, ומציין במפורש איזה חלק מהתחום תלוי במדידה.
    """
    if not frontage_widths:
        return {"floors_low": None, "floors_high": None, "certain": False,
                "needs_measurement": False, "why": "אין חזית רחוב מזוהה"}

    lows, highs, notes = [], [], []
    certain = True
    risk = 0.0
    for w in frontage_widths:
        b = floors_band(w, tol)
        certain &= b["certain"]
        risk = max(risk, b["none_share"] + b["undef_share"])
        if b["low"] is None:
            why = b["undef_why"] or "עד 8 מ׳ — לא תותר תוספת"
            return {"floors_low": None, "floors_high": None, "certain": b["certain"],
                    "needs_measurement": not b["certain"],
                    "why": f"חזית {w} מ׳ (±{tol}): {why}"}
        lows.append(b["low"]); highs.append(b["high"])
        tag = f"{w}→{b['low']}" if b["certain"] else f"{w}→{b['low']}–{b['high']}"
        if b["none_share"] or b["undef_share"]:
            tag += f" ({100 * (b['none_share'] + b['undef_share']):.0f}% מהתחום ללא מספר)"
        notes.append(tag)

    lo = min(min(lows), map_cap)               # החזית הצרה קובעת, והמפה חוסמת
    hi = min(min(highs), map_cap)
    if risk > 0.5:
        # רוב התחום אינו מקבל מספר מהמדיניות. מספר בכותרת יטעה גם עם דגל.
        return {"floors_low": None, "floors_high": None, "certain": False,
                "needs_measurement": True, "risk_share": round(risk, 2),
                "why": f"חזיתות {', '.join(notes)} — רוב תחום המדידה ללא מספר במדיניות"}
    head = f"{lo}" if lo == hi else f"{lo}–{hi}"
    if not certain:
        head += " (דורש מדידה)"
    return {"floors_low": lo, "floors_high": hi,
            "certain": certain and lo == hi,
            "needs_measurement": not certain,
            "risk_share": round(risk, 2),
            "why": f"חזיתות {', '.join(notes)} · מפה {map_cap} → {head}"}
