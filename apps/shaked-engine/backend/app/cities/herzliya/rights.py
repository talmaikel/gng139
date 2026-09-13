"""שרשרת הזכויות של חלופת שקד בהרצליה — תשעה שלבים, וכל אחד עם אסמכתה.

הועבר מ-`POC/layer_a/scripts` ולא מיובא ממנו, לפי כלל הבידוד: ה-engine
אינו תלוי ב-POC. כל מספר כאן מצוטט למקורו, ומי שמשנה אותו צריך לשנות גם
את ההפניה.

**מה שקל לטעות בו, ולכן כתוב במפורש:**

‏§70א מונה שלושה תנאי סף — מועד ההיתר, שלא בוצע חיזוק, ושני קומות וארבע
דירות. **שטח בנוי אינו אחד מהם.** הוא נכנס רק ב-§70ב, בחישוב הזכויות.
לכן שטח קיים לעולם אינו שדה כשירות כאן, וההערכה שלו אינה יכולה לפסול.

‏400% הוא על השטח הכולל **מעל הקרקע וכולל שטחי שירות וממ״ד** — לא על
השטח העיקרי בלבד.

טבלת רוחב הרחוב אינה רציפה: עד 8 מ׳ אין תוספת, **8–9 מ׳ אינו מוגדר בה
כלל**, ומעל 15 מ׳ היא מפנה למדיניות מרכז העיר — שם תקרת הקטגוריה קובעת
ולא הרחוב. החזית הצרה קובעת, לא הרחבה.

מספר הקומות בטבלה **כולל את קומת הקרקע** (הערה 1 לטבלה).

והסייג שחייב להופיע בכל תיק, הערה 1 לטבלת התכנית האסטרטגית: *״התכנית
הינה מדיניות בלבד. הוועדה המקומית רשאית לקבוע מס׳ קומות ונפחים שונים
בהתאם לשיקול דעתה״*. כל מספר כאן הוא **תקרה נתונה לבחינה, לא זכות**.
"""
from dataclasses import dataclass, field as dc_field

POLICY_URL = (
    "https://handasa.herzliya.muni.il/wp-content/uploads/2026/04/"
    "%D7%9E%D7%93%D7%99%D7%A0%D7%99%D7%95%D7%AA-%D7%91%D7%A0%D7%99%D7%94-"
    "%D7%97%D7%9C%D7%95%D7%A4%D7%AA-%D7%A9%D7%A7%D7%93-%D7%90%D7%A4%D7%A8%D7%99%D7%9C-2026.pdf"
)
STRATEGIC_URL = (
    "https://handasa.herzliya.muni.il/wp-content/uploads/2023/09/"
    "%D7%AA%D7%9B%D7%A0%D7%99%D7%AA-%D7%90%D7%A1%D7%98%D7%A8%D7%98%D7%92%D7%99%D7%AA-"
    "%D7%9C%D7%94%D7%AA%D7%97%D7%93%D7%A9%D7%95%D7%AA-%D7%9E%D7%A8%D7%9B%D7%96-"
    "%D7%94%D7%A2%D7%99%D7%A8-%D7%99%D7%A0%D7%95%D7%90%D7%A8-2023.pdf"
)
PARKING_URL = (
    "https://handasa.herzliya.muni.il/wp-content/uploads/2026/04/"
    "%D7%AA%D7%A7%D7%9F-%D7%97%D7%A0%D7%99%D7%94-2025-"
    "%D7%9B%D7%95%D7%9C%D7%9C-%D7%94%D7%97%D7%9C%D7%98%D7%AA-%D7%94%D7%95%D7%A2%D7%93%D7%94.pdf"
)
RULE_VERSION = "herzliya-shaked-2026-02-17"

TOLERANCE_M = 1.0        # הנחה, לא מדידה. ראה validation/street_width.csv
RELIABLE_MAX_M = 15.0    # מעליו מדידת הפער אינה אמינה — וגם אינה נדרשת
UNBOUND = float("inf")   # הרחוב אינו מגביל; תקרת הקטגוריה קובעת

# מדיניות §5, "גובה אל מול חתך הרחוב" (עמ׳ 8). (גבול עליון כולל, מקסימום קומות)
#
# הטבלה אינה רציפה, ולכן שני הגבולות הראשונים אינם בטבלה אלא בקוד:
# "עד 8 מ׳ **כולל**" → אין תוספת, והשורה הבאה מתחילה ב-"9-10 מ׳". התחום
# שבין 8 ל-9 אינו מופיע בטבלה כלל. **9.0 עצמו שייך לשורת ה-9–10**, ולכן
# הפער הוא 8 &lt; w &lt; 9 ולא 8 &lt; w ≤ 9 — הגבול שעליו כתוב ב-README שהוא
# ההבדל בין פרויקט לכלום.
STREET_TABLE = [(10.0, 7), (12.0, 8), (15.0, 9)]
NO_ADDITION_MAX = 8.0
UNDEFINED_BELOW = 9.0

CATEGORY_CEILING = {"התחדשות מגרשית מוטת מגורים": 9.0,
                    "התחדשות מגרשית מוטת מגורים נמוכה": 5.5}

# מדיניות §8: רצפת ההפרשה לשב"צ, לפי אזור רישום.
ALLOCATION_FLOOR_300 = {"אלון", "ברנר", "גן רש\"ל", "הנדיב", "יוחנני", "נוף ים", "נוף-ים", "שז\"ר"}
ALLOCATION_FLOOR_400 = {"בן צבי", "ברנדיס", "ברנדייס", "ויצמן", "יצחק נבון", "לב טוב", "הירוק"}

# תקן חניה 2025 ס׳א.1. עליהם לא יותרו כניסות חדשות לרכבים (ס׳א.2).
MAIN_AXES = {"דרך ירושלים", "העצמאות", "הרב קוק", "ארלוזורוב", "סוקולוב",
             "ויצמן", "בן גוריון", "הבריגדה היהודית", "ז'בוטינסקי"}


@dataclass
class Check:
    id: str
    label: str
    status: str            # passed | failed | unknown | routed | undefined
    source_url: str
    page: int | None = None
    detail: str | None = None


@dataclass
class Rights:
    checks: list[Check] = dc_field(default_factory=list)
    floors_low: float | None = None
    floors_high: float | None = None
    floors_certain: bool = False
    case_by_case: bool = False
    notes: list[str] = dc_field(default_factory=list)


# ─────────────────────────── §70א · תנאי הסף ───────────────────────────

def threshold_checks(f: dict) -> list[Check]:
    """שלושת תנאי §70א. שטח בנוי אינו אחד מהם, ולכן אינו נבדק כאן."""
    out = []

    permit, opinion = f.get("permit_date"), f.get("engineer_opinion")
    if permit is None:
        status, detail = "unknown", "מועד ההיתר אינו ידוע — נדרש תיק בניין"
    elif str(permit) < "1980-01-01":
        status, detail = "passed", f"היתר {str(permit)[:4]}"
    elif str(permit) <= "1984-12-31":
        status = "passed" if opinion is True else "unknown"
        detail = "1980–1984 מחייב חוות דעת מהנדס" + ("" if opinion is True else " — אינה בידינו")
    else:
        status, detail = "failed", f"היתר {str(permit)[:4]} — אחרי 1984"
    out.append(Check("permit_date", "מועד היתר, וחוות דעת אם 1980–1984", status,
                     POLICY_URL, 3, detail))

    s = f.get("strengthened")
    out.append(Check("strengthened", "לא בוצע חיזוק מכוח היתר",
                     "unknown" if s is None else ("passed" if s is False else "failed"),
                     POLICY_URL, 3,
                     None if s is None else ("לא נמצאה בקשת חיזוק עם היתר" if not s else "חוזק — §70א(2)")))

    # ״תפוס״ אינו תנאי סף בחוק — מבנה כזה כשיר לחלוטין. הוא פשוט אינו
    # זמין: בקשת חיזוק שהוגשה ולא הבשילה להיתר פירושה שיזם אחר כבר עובד
    # מול הדיירים. לכן `routed` ולא `failed` — ניתוב, לא פסילה.
    occ = f.get("occupied")
    out.append(Check("occupied", "לא נמצאה יוזמת התחדשות פעילה של אחר",
                     "unknown" if occ is None else ("passed" if occ is False else "routed"),
                     POLICY_URL, None,
                     None if occ is None else
                     ("אין בקשת חיזוק פתוחה" if not occ else
                      "בקשת חיזוק ללא היתר — יזם אחר כבר מול הדיירים")))

    fl, un = f.get("floors"), f.get("units")
    out.append(Check("floors", "לפחות שתי קומות מעל הקרקע",
                     "unknown" if fl is None else ("passed" if fl >= 2 else "failed"),
                     POLICY_URL, 3, None if fl is None else f"{fl} קומות"))
    out.append(Check("units", "לפחות ארבע דירות שנבנו בהיתר",
                     "unknown" if un is None else ("passed" if un >= 4 else "failed"),
                     POLICY_URL, 3, None if un is None else f"{un} דירות"))
    return out


# ─────────────────────── שלב 4 · גובה מול חתך הרחוב ───────────────────────

def floors_for_width(width_m: float | None):
    """מקסימום קומות לחזית אחת. מחזיר מספר, None (אין תוספת),
    'undefined' (הפער 8–9), או UNBOUND (מעל 15 — הרחוב אינו מגביל)."""
    if width_m is None:
        return "unknown"
    if width_m <= NO_ADDITION_MAX:
        return None
    if width_m < UNDEFINED_BELOW:          # 9.0 עצמו כבר בשורת 9–10
        return "undefined"
    for upper, result in STREET_TABLE:
        if width_m <= upper:
            return result
    return UNBOUND


def floors(width_m: float | None, category: str | None, tol: float = TOLERANCE_M) -> Rights:
    """תקרת הקטגוריה, מוקטנת לפי רוחב הרחוב.

    סורק את כל התחום [w-tol, w+tol] בצעדים של 0.1 מ׳ — פער לא מוגדר שנופל
    *בתוך* התחום ולא על קצותיו נתפס כך גם הוא.
    """
    r = Rights()
    ceiling = CATEGORY_CEILING.get(category or "")
    if ceiling is None:
        r.checks.append(Check("renewal_policy_category", "קטגוריה במפת המדיניות",
                              "unknown", STRATEGIC_URL, 8, "אין קטגוריה מזוהה"))
        return r
    r.checks.append(Check("renewal_policy_category", "קטגוריה במפת המדיניות",
                          "passed", STRATEGIC_URL, 8, f"{category} · תקרה {ceiling}"))

    if width_m is None:
        r.checks.append(Check("street_width", "רוחב רחוב", "unknown", POLICY_URL, 8,
                              "לא נמדד — לא ניתן להקטין את התקרה"))
        return r

    seen, none_hits, undefined_hits = [], 0, 0
    steps = max(int(2 * tol / 0.1), 1)
    for i in range(steps + 1):
        v = floors_for_width(max(width_m - tol + i * 0.1, 0.01))
        if v is None:
            none_hits += 1
        elif v == "undefined":
            undefined_hits += 1
        else:
            seen.append(min(v, ceiling) if v != UNBOUND else ceiling)

    total = steps + 1
    if not seen:
        r.checks.append(Check("street_width", "רוחב רחוב", "failed", POLICY_URL, 8,
                              _width_text(width_m) + " — לא תותר תוספת"))
        return r

    r.floors_low, r.floors_high = min(seen), max(seen)
    r.floors_certain = len(seen) == total and r.floors_low == r.floors_high
    r.case_by_case = width_m > RELIABLE_MAX_M
    status = "passed" if r.floors_certain else "undefined"
    bits = [_width_text(width_m)]
    if none_hits or undefined_hits:
        bits.append(f"{100*(none_hits+undefined_hits)//total}% מתחום המדידה ללא מספר במדיניות")
    if r.case_by_case:
        bits.append("מעל 15 מ׳ — הרחוב אינו מגביל, תקרת הקטגוריה קובעת ונתונה לבחינה נקודתית")
    r.checks.append(Check("street_width", "רוחב רחוב מול מספר קומות", status,
                          POLICY_URL, 8, " · ".join(bits)))
    r.notes.append("הערה 1 לטבלת הר/2323: מדיניות בלבד; הוועדה רשאית לקבוע אחרת.")
    return r


def _width_text(w: float) -> str:
    return f"מעל {RELIABLE_MAX_M:.0f} מ׳ (הערך המדויק אינו אמין)" if w > RELIABLE_MAX_M else f"{w:.1f} מ׳"


# ───────────────────────── שלבים 6–9 ─────────────────────────

def allocation(total_after: float, registration_area: str | None):
    """שלב 6 · הפרשה לשב״צ: 10%, עם רצפה לפי אזור רישום. מתחת לרצפה — אין."""
    if registration_area is None:
        return None, "אזור הרישום אינו ידוע"
    floor = 300 if registration_area in ALLOCATION_FLOOR_300 else \
        400 if registration_area in ALLOCATION_FLOOR_400 else None
    if floor is None:
        return None, f"אזור {registration_area} אינו ברשימות הרצפה במדיניות §8"
    ten = total_after * 0.10
    return (ten, f"10% = {ten:,.0f} ≥ רצפת {floor}") if ten >= floor else \
        (0.0, f"10% = {ten:,.0f} מתחת לרצפת {floor} — אין הפרשה")


def balconies(units: int) -> tuple[float, str]:
    """שלב 7 · מרפסות. **מוסיף** ואינו מנכה: המדיניות קובעת שהן בנוסף."""
    return units * 12.0, f'{units} יח"ד × 12 מ"ר ממוצע מקסימלי (§2ו)'


def unit_mix(existing_units: int, sellable_main: float | None = None) -> dict:
    """שלב 8 · תמהיל. מדיניות §4: קיים × 2.8–3.18, ולפחות 25% קטנות 56–80."""
    lo, hi = round(existing_units * 2.8), round(existing_units * 3.18)
    out = {"units_min": lo, "units_max": hi, "small_min": round(hi * 0.25),
           "micro_max": round(hi * 0.25 * 0.10), "accessible": round(hi * 0.10)}
    if sellable_main:
        out["avg_unit_at_max"] = round(sellable_main / hi, 1)
        out["mix_feasible"] = out["avg_unit_at_max"] >= 56
    return out


def parking(units: int, in_tama70: bool | None, unit_areas: list[float] | None = None) -> dict:
    """שלב 9 · חניה, לפי תקן ועדת משנה 769 מ-10.09.2025.

    `in_tama70` נדרש במפורש ואין לו ברירת מחדל: 72% מהמועמדים בתוך תמ״א 70
    ו-28% מחוצה לה, וההבדל הוא רבע ממספר החניות.
    """
    if in_tama70 is None:
        return {"spaces": None, "why": 'לא ידוע אם בתוך תמ"א 70 — התקן 1.0 מול 1.5'}
    if in_tama70:
        return {"spaces": units * 1.0, "per_unit": 1.0,
                "why": 'תמ"א 70, מדד נגישות 1+2 — 1.0 ליח"ד',
                "caveat": "מדד הנגישות נקבע במיפוי תמ״א 70; כאן נקרא מטבלה מסומנת ידנית"}
    if unit_areas is None:
        return {"spaces": units * 1.5, "per_unit": 1.5,
                "why": 'מחוץ לתמ"א 70 — 1.5 ליח"ד, ללא הנחות לדירות קטנות'}
    spaces, small = 0.0, 0
    for a in unit_areas:
        if a <= 30:
            small += 1                      # תקן 0, אך חובה מרתף עם חניות נגישות
        elif a <= 65:
            spaces += 1.0; small += 1
        else:
            spaces += 1.5
    return {"spaces": round(spaces, 1), "per_unit": round(spaces / units, 2),
            "guests": round(small * 0.20, 1),
            "why": f'מחוץ לתמ"א 70 · {units - small} × 1.5 + {small} קטנות · אורחים 20%'}


def main_axis_only(street_names: list[str]) -> str | None:
    """מסומן רק כשכל החזיתות על ציר ראשי — לחלקה עם חזית שנייה יש חלופה."""
    axes = [n for n in street_names if any(a in n for a in MAIN_AXES)]
    if not axes or len(axes) != len(street_names):
        return None
    return ("כל החזיתות על ציר ראשי (" + ", ".join(sorted(set(axes))) +
            ") — תקן החניה 2025 ס׳א.2 אינו מבטיח כניסה חדשה לרכבים")


def cap_400(existing_area: float | None) -> tuple[float | None, str]:
    """שלב 2 · §70ב(א)(1). כולל שטחי שירות וממ״ד, לא רק עיקרי."""
    if existing_area is None:
        return None, "השטח הקיים אינו ידוע — אומדן בלבד, ואינו תנאי סף"
    return existing_area * 4, f"400% × {existing_area:,.0f} מ\"ר (כולל שירות וממ\"ד)"
