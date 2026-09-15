"""שרשרת הזכויות של חלופת שקד בהרצליה — תשעה שלבים, וכל אחד עם אסמכתה.

הועבר מ-`POC/layer_a/scripts` ולא מיובא ממנו, לפי כלל הבידוד: ה-engine
אינו תלוי ב-POC. כל מספר כאן מצוטט למקורו, ומי שמשנה אותו צריך לשנות גם
את ההפניה.

**מה שקל לטעות בו, ולכן כתוב במפורש:**

‏§70א אינו שלושה תנאים אלא **הגדרה** שכולה תנאי סף, כפי שהמדיניות אומרת
במפורש: *״תנאי סף לקידום תכנית בחלופת שקד הינו עמידה בהגדרות סעיף 70א״*.
לשון ההגדרה:

  *״בנין הנמצא במגרש המיועד לפי תכנית **גם למגורים**, ש-**70% לפחות
  משטח הבנייה הכולל הקיים שלו משמש כדין למגורים**, ובכלל זה לשטחי שירות
  למגורים, ושמתקיימים בו כל אלה: (1)(2)(3)״*

כלומר **חמישה** שערים ולא שלושה. גרסה קודמת של הקובץ הזה מנתה שלושה
בלבד וקבעה ש״שטח בנוי אינו אחד מהם״ — זו הייתה קריאה של הסעיפים
הממוספרים בלבד, ומבחן ה-70% הוא דווקא **כן** מבחן על שטח בנוי. בניין
שנכשל בו דווח ככשיר.

מה שנשאר נכון מאותה קריאה: השטח הקיים אינו נכנס לתקרת הזכויות כשדה
כשירות. הוא נכנס ב-§70ב, בחישוב, ולכן אומדן שלו אינו פוסל איש — אבל
**היחס** בין שימוש למגורים לשטח הכולל כן.

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

# גרסת הכללים שלפיה מחושבות הזכויות. קשורה למסמך המדיניות שאומת מול
# הפרסום של אפריל 2026 — זהה אות-באות, 14 עמודים, 13,838 תווים. כל שינוי
# בטבלת רוחב הרחוב, בתקרות הקטגוריה או בתקן החניה מחייב העלאה כאן, אחרת
# תיק שנמסר לא יידע לפי מה הוא חושב.
RULES_VERSION = "herzliya-policy-2026-02+w2026-09-15"

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
# שני הקבועים נשענים על מדידה ידנית ב-GovMap (D1, 14.09.2026):
# ‏POC/layer_a/validation/street_width.csv ו-d1_followup.json.
#
# ‏TOLERANCE_M — ב-9 רחובות שהמנוע נתן להם עד 12.1 מ׳, השגיאה מול המדידה
# הייתה עד 0.8 מ׳ (חציון 0.5, בלי הטיה). שני מודדים על אותן שלוש חלקות
# נבדלו עד 0.8 מ׳ (ממוצע 0.4). ‏1.0 מכסה את שניהם.
TOLERANCE_M = 1.0
#
# ‏RELIABLE_MAX_M — מעליו מדידת הפער מגזימה, ולא בגבולות הסבילות: הראשונים
# 14.0→10.8, מלכי יהודה 20.6→11.3, שווידלסון 33.0→10.4, ורופין 10 קיבלה
# 29.1 כשהחזית שלה 9.9. הקרן בורחת מעבר לחלקה שממול, ולכן השגיאה חד-כיוונית:
# הערך הוא חסם עליון, לא מדידה. ‏12.1 הוא הערך הגבוה ביותר שאומת, ו-12 הוא
# גם הגבול שממנו הטבלה נותנת 9 קומות.
#
# ‏15.09: הרוחבות עברו ל-frontages_v2 (הקרן נעצרת בחלקה הבנויה שממול). מול 29
# חזיתות שנמדדו ביד — 27 בתוך ±1 מ׳. אבל במדגם אקראי של 10 מעל 12 מ׳ עדיין
# הגזמה אחת שהעבירה חזית מ-11 ל-17.9 (ליברמן), ולכן הסף נשאר.
RELIABLE_MAX_M = 12.0
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

# שכבת ה-GIS ומסמך המדיניות קוראים לאותו אזור בשני שמות. השוואת מחרוזת
# מדויקת החזירה ״אינו ברשימות הרצפה״, ושלוש חלקות יצאו **בלי רצפת
# ההפרשה לשב״צ** — כלומר נראו רווחיות יותר משהן, בלי שגיאה ובלי סימן.
#
# ‏**כל שורה כאן היא החלטה אנושית ולא ניחוש.** מיפוי שמות אזורים משנה
# זכויות, ולכן אינו נגזר מדמיון מחרוזות. אושר על ידי בועז, 14.09.2026,
# מול נוסח המדיניות: ״...ויצמן, יצחק נבון, לב טוב והירוק.״
AREA_ALIASES = {
    "בית ספר ירוק (שם זמני)": "הירוק",
}


def canonical_area(name: str | None) -> str | None:
    """שם האזור כפי שהמדיניות מכירה אותו."""
    return AREA_ALIASES.get(name, name)

# תקן חניה 2025 ס׳א.1. עליהם לא יותרו כניסות חדשות לרכבים (ס׳א.2).
MAIN_AXES = {"דרך ירושלים", "העצמאות", "הרב קוק", "ארלוזורוב", "סוקולוב",
             "ויצמן", "בן גוריון", "הבריגדה היהודית", "ז'בוטינסקי"}


@dataclass
class Check:
    id: str
    label: str
    # passed | failed | unknown | routed | undefined | needs_measurement
    #
    # ‏`undefined` = המדיניות שותקת. ‏`needs_measurement` = המדיניות ברורה
    # והמדידה שלנו אינה. שניהם אינם ״עבר״, ושניהם מובילים לפעולה אחרת.
    status: str
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

# שערי §70א עצמם, לפי סדר ההגדרה. לכל אחד יש סעיף לצטט.
SECTION_70A_IDS = ("residential_zoning", "residential_share", "permit_date",
                   "strengthened", "floors", "units")

# השערים שחייבים תשובה לפני מסירה. ששה מהם הם §70א, והשביעי — `occupied` —
# **אינו תנאי סף בחוק**: בקשת חיזוק שהוגשה ולא הבשילה להיתר פירושה שיזם
# אחר כבר מול הדיירים. המגרש כשיר בדין ואינו זמין בפועל, ולכן אין לו עמוד
# לצטט ואין להציג אותו כסעיף בחוק. השם הקודם היה `THRESHOLD_IDS` בלבד,
# והוא הציג את השער המסחרי הזה כאילו הוא §70א.
THRESHOLD_IDS = SECTION_70A_IDS + ("occupied",)

# שער שאין לו מקור פתוח, ולכן ״לא ידוע״ בו אינו מעיד על עבודה חסרה אלא על
# גבול הנתונים. הוא נשאר שאלה פתוחה בתיק ואינו פוסל מסירה — אבל הוא גם
# לעולם לא ייקרא כ״עבר״: `threshold_checks` מחזיר בו unknown, והסטטוס יורד
# ל-needs_verification בכל מקרה.
UNOBTAINABLE = {"residential_share"}


def threshold_checks(f: dict) -> list[Check]:
    """חמשת תנאי §70א: שניים מההגדרה עצמה ושלושה מהסעיפים הממוספרים."""
    out = []

    # ── שני התנאים שבגוף ההגדרה ──
    zoning = f.get("residential_zoning")
    out.append(Check("residential_zoning", "המגרש מיועד בתכנית גם למגורים",
                     "unknown" if zoning is None else ("passed" if zoning else "failed"),
                     POLICY_URL, 3,
                     None if zoning is None else ("ייעוד מגורים בתכנית מקומית" if zoning
                                                  else "אין ייעוד מגורים")))

    share = f.get("residential_share")
    out.append(Check("residential_share", "לפחות 70% מהשטח הבנוי משמש כדין למגורים",
                     "unknown" if share is None else ("passed" if share >= 0.7 else "failed"),
                     POLICY_URL, 3,
                     "לא ניתן לגזור ממקורות פתוחים — שכבת השימושים ריקה ב-97% מהנקודות"
                     if share is None else f"{share:.0%}"))

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
    # §70א(3) קובע כלל ספירה משלו: קומת עמודים **נספרת**, וקומה עליונה
    # ששטחה פחות ממחצית זו שמתחתיה **אינה**. ‏Num_floors בשכבה העירונית
    # הוא ספירה פיזית ואינו מיישם אותו, ולכן הערך נשא סייג ולא שתיקה.
    out.append(Check("floors", "לפחות שתי קומות מעל הקרקע",
                     "unknown" if fl is None else ("passed" if fl >= 2 else "failed"),
                     POLICY_URL, 3,
                     None if fl is None else
                     f"{fl} קומות · ספירה פיזית; כלל הספירה של §70א(3) לא הוחל"))
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


def floors(width_m: float | None, category: str | None, tol: float = TOLERANCE_M, *,
           verified: bool = True, narrow: str | None = None) -> Rights:
    """תקרת הקטגוריה, מוקטנת לפי רוחב הרחוב.

    סורק את כל התחום [w-tol, w+tol] בצעדים של 0.1 מ׳ — פער לא מוגדר שנופל
    *בתוך* התחום ולא על קצותיו נתפס כך גם הוא.

    ‏`verified=False` — הרוחב בא מהאלגוריתם הקודם, שהגזים עקבית, כי החדש לא
    מצא חזית. מתייחסים אליו כחסם עליון בכל גובה, לא רק מעל RELIABLE_MAX_M.

    ‏`narrow` — חזית צרה מ-8 מ׳ שהאלגוריתם מצא. אם היא רחוב, אין תוספת; אם
    היא דרך שירות או כניסה לחניון, היא לא נספרת. באימות 3 מתוך 6 היו כל
    אחד מהשניים, ולכן היא לא מכריעה — אבל שום מספר כאן אינו ודאי לידה.
    """
    r = Rights()
    ceiling = CATEGORY_CEILING.get(category or "")
    if ceiling is None:
        r.checks.append(Check("renewal_policy_category", "קטגוריה במפת המדיניות",
                              "unknown", STRATEGIC_URL, 8, "אין קטגוריה מזוהה"))
        return r
    r.checks.append(Check("renewal_policy_category", "קטגוריה במפת המדיניות",
                          "passed", STRATEGIC_URL, 8, f"{category} · תקרה {ceiling}"))

    narrow_text = (f"חזית צרה מ-8 מ׳: {narrow} — אם זה רחוב, אין תוספת; "
                   "אם דרך שירות או חניון, היא לא נספרת") if narrow else None

    if width_m is None:
        r.checks.append(Check("street_width", "רוחב רחוב", "unknown", POLICY_URL, 8,
                              " · ".join(filter(None, ["לא נמדד — לא ניתן להקטין את התקרה", narrow_text]))))
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

    # מעל RELIABLE_MAX_M הרחוב האמיתי עשוי להיות צר בהרבה, ולכן התחום נפתח
    # כלפי מטה עד השורה הממוספרת הראשונה בטבלה. בלי זה, 33 מ׳ יצא ״9 קומות,
    # עבר״ — וארלוזורוב 5 נמדדה 8.
    unreliable = width_m > RELIABLE_MAX_M or not verified
    if unreliable:
        seen.append(min(STREET_TABLE[0][1], ceiling))

    r.floors_low, r.floors_high = min(seen), max(seen)
    r.floors_certain = (none_hits + undefined_hits == 0 and r.floors_low == r.floors_high
                        and not narrow)
    # ״בחינה נקודתית״ נכונה רק לרחוב שידוע שהוא מעל 15 מ׳, ומדידת פער כזו אינה אמינה.
    r.case_by_case = not unreliable and width_m > STREET_TABLE[-1][0]

    # **שני דברים שונים, ולא סטטוס אחד.** ‏11.5 מ׳ נופל בבירור בשורת
    # ״10-12״ ומקבל 8 קומות — המדיניות מוגדרת לחלוטין. מה שאינו ודאי הוא
    # **המדידה שלנו**: ±1 מ׳ חוצה לשורה הבאה. הגרסה הקודמת החזירה
    # ״undefined״ בשני המקרים, והקורא הבין ״המדיניות אינה מכסה את זה״
    # במקום ״צריך למדוד את הרחוב״ — שתי מסקנות הפוכות לגמרי לגבי מה
    # לעשות הלאה.
    policy_silent = (none_hits + undefined_hits) > 0
    if r.floors_certain:
        status, label = "passed", "רוחב רחוב מול מספר קומות"
    elif policy_silent:
        status, label = "undefined", "רוחב רחוב — המדיניות אינה מכסה חלק מהתחום"
    else:
        status, label = "needs_measurement", "רוחב רחוב — המדידה אינה חד-משמעית"

    bits = [_width_text(width_m)]
    if policy_silent:
        bits.append(f"{100*(none_hits+undefined_hits)//total}% מתחום המדידה ללא מספר במדיניות")
    elif not verified and r.floors_low != r.floors_high:
        bits.append(f"רוחב מהאלגוריתם הקודם, שהגזים — לא מאומת; "
                    f"{r.floors_low:g} עד {r.floors_high:g} קומות; מדידה בשטח תכריע")
    elif unreliable and r.floors_low != r.floors_high:
        bits.append(f"מדידת הפער מגזימה ברחובות רחבים — הרחוב עשוי להיות צר בהרבה; "
                    f"{r.floors_low:g} עד {r.floors_high:g} קומות; מדידה בשטח תכריע")
    elif r.floors_low != r.floors_high:
        bits.append(f"טווח ±{tol:g} מ׳ חוצה שורות בטבלה — {r.floors_low:g} עד {r.floors_high:g} קומות; "
                    "מדידה בשטח תכריע")
    if r.case_by_case:
        bits.append("מעל 15 מ׳ — הרחוב אינו מגביל, תקרת הקטגוריה קובעת ונתונה לבחינה נקודתית")
    if narrow_text:
        bits.append(narrow_text)
    r.checks.append(Check("street_width", "רוחב רחוב מול מספר קומות", status,
                          POLICY_URL, 8, " · ".join(bits)))
    r.notes.append("הערה 1 לטבלת הר/2323: מדיניות בלבד; הוועדה רשאית לקבוע אחרת.")
    return r


def _width_text(w: float) -> str:
    return f"מעל {RELIABLE_MAX_M:.0f} מ׳ (הערך המדויק אינו אמין)" if w > RELIABLE_MAX_M else f"{w:.1f} מ׳"


# ───────────────────────── שלבים 6–9 ─────────────────────────

def allocation(total_after: float, registration_area: str | None,
               total_is_ceiling: bool = False):
    """שלב 6 · הפרשה לשב״צ: 10%, עם רצפה לפי אזור רישום. מתחת לרצפה — אין.

    ‏`total_after` הוא **סך השטחים בתכנית לאחר ההגדלה** (מדיניות עמ׳ 13
    §8ה) — מה שהתכנית מציעה בפועל. תקרת ה-400% אינה זה: היא החסם העליון
    שהתכנית מותרת להגיע אליו. הזנת התקרה נותנת הפרשה מקסימלית, וזו תשובה
    שימושית בשלב הסינון אבל היא חסם ולא חישוב — `total_is_ceiling` מסמן
    אותה ככזו בנימוק, כדי שלא תיקרא כשטח ההפרשה שייקבע בתכנית.
    """
    if registration_area is None:
        return None, "אזור הרישום אינו ידוע"
    registration_area = canonical_area(registration_area)
    floor = 300 if registration_area in ALLOCATION_FLOOR_300 else \
        400 if registration_area in ALLOCATION_FLOOR_400 else None
    if floor is None:
        return None, f"אזור {registration_area} אינו ברשימות הרצפה במדיניות §8"
    ten = total_after * 0.10
    basis = " · על תקרת 400% ולא על סך השטחים המוצע — חסם עליון" if total_is_ceiling else ""
    return (ten, f"10% = {ten:,.0f} ≥ רצפת {floor}{basis}") if ten >= floor else \
        (0.0, f"10% = {ten:,.0f} מתחת לרצפת {floor} — אין הפרשה{basis}")


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

    שתי שורות בתקן שהיו כאן שגויות, ושתיהן בכיוון שמקטין את הדרישה:

    * **חניות אורחים הן 20% ממספר יחידות הדיור** — ״ידרשו 20% ממספר יח״ד
      לתקן חניות אורחים״ — ולא 20% מהדירות הקטנות. הסעיף חל ״בתבע״ות שבהם
      תקן החניה 0-1:1״, כלומר רק כשהתקן האפקטיבי אינו עולה על 1.0, וניתן
      להקטינו ל-10% באישור הוועדה המקומית.
    * **10% חניות נגישות במרתף** נמדדות ממספר הדירות **עד 30 מ״ר** בלבד,
      והן ״בנוסף לתקן הרגיל״ ואינן מוצמדות.

    סעיף האורחים יושב בפרק ג.2 — ״מחוץ לטווח תמ״א 70״. בתוך תמ״א 70 התקן
    נקבע בהוראות תמ״א 70 עצמה, ולכן כאן הוא מסויג ואינו מחושב.
    """
    if in_tama70 is None:
        return {"spaces": None, "why": 'לא ידוע אם בתוך תמ"א 70 — התקן 1.0 מול 1.5'}
    if in_tama70:
        return {"spaces": units * 1.0, "per_unit": 1.0,
                "why": 'תמ"א 70, מדד נגישות 1+2 — 1.0 ליח"ד',
                "caveat": "מדד הנגישות נקבע במיפוי תמ״א 70; כאן נקרא מטבלה מסומנת ידנית · "
                          "סעיף חניות האורחים במדיניות חל מחוץ לתמ״א 70, ובתוכה קובעות "
                          "הוראות תמ״א 70 — ולכן אינו מחושב כאן"}
    if unit_areas is None:
        return {"spaces": units * 1.5, "per_unit": 1.5,
                "why": 'מחוץ לתמ"א 70 — 1.5 ליח"ד, ללא הנחות לדירות קטנות'}

    micro = sum(1 for a in unit_areas if a <= 30)          # תקן 0
    compact = sum(1 for a in unit_areas if 30 < a <= 65)   # תקן 1.0
    full = len(unit_areas) - micro - compact               # תקן 1.5
    spaces = compact * 1.0 + full * 1.5
    per_unit = round(spaces / units, 2) if units else None

    out = {"spaces": round(spaces, 1), "per_unit": per_unit,
           "accessible_basement": round(micro * 0.10, 1),
           "why": f'מחוץ לתמ"א 70 · {full} × 1.5 + {compact} × 1.0 + {micro} עד 30 מ"ר בתקן 0'}
    if per_unit is not None and per_unit <= 1.0:
        out["guests"] = round(units * 0.20, 1)
        out["guests_why"] = ('20% ממספר יח"ד — התקן האפקטיבי 0-1:1 · '
                             "ניתן להקטין ל-10% באישור הוועדה המקומית")
    else:
        out["guests"] = 0.0
        out["guests_why"] = (f"התקן האפקטיבי {per_unit} עולה על 1:1 — "
                             "סעיף חניות האורחים אינו חל")
    if micro:
        out["accessible_why"] = f'10% מ-{micro} דירות עד 30 מ"ר · בנוסף לתקן ולא מוצמדות'
    return out


def main_axis_only(street_names: list[str]) -> str | None:
    """מסומן רק כשכל החזיתות על ציר ראשי — לחלקה עם חזית שנייה יש חלופה."""
    axes = [n for n in street_names if any(a in n for a in MAIN_AXES)]
    if not axes or len(axes) != len(street_names):
        return None
    return ("כל החזיתות על ציר ראשי (" + ", ".join(sorted(set(axes))) +
            ") — תקן החניה 2025 ס׳א.2 אינו מבטיח כניסה חדשה לרכבים")

def cap_400(existing_area: float | None,
            post_2005: float | bool | None = None) -> tuple[float | None, str]:
    """שלב 2 · §70ב(א)(1). כולל שטחי שירות וממ״ד, לא רק עיקרי.

    ‏§70ב(א)(1)(ב) מחריג מהבסיס תוספת בנייה שהותרה **אחרי 18.5.2005**.
    בלי ההחרגה הבסיס מנופח לכל בניין שהורחב מאז, והשגיאה מוכפלת פי ארבע.

    ‏`post_2005` נושא ארבעה מצבים ולא שניים, כי ״לא נבדק״ ו״נבדק ואין״
    נראים אותו דבר אם שואלים רק כן/לא:

      ``None``   — לא נבדק
      ``False``  — נבדק, אין תוספת שהותרה אחרי המועד
      ``True``   — נבדק, יש היתר אחרי המועד ושטחו אינו ידוע
      ``float``  — שטח התוספת, להחרגה בפועל
    """
    if existing_area is None:
        return None, "השטח הקיים אינו ידוע — אומדן בלבד, ואינו תנאי סף"

    excluded = post_2005 if _is_area(post_2005) else 0.0
    base = existing_area - excluded
    why = f'400% × {base:,.0f} מ"ר (כולל שירות וממ"ד)'
    if excluded:
        why += f' · הוחרגה תוספת של {excluded:,.0f} מ"ר שהותרה אחרי 18.5.2005'
    elif post_2005 is True:
        # ‏B8 · היה ״והתקרה כאן מנופחת״. היתר אחרי המועד אינו בהכרח תוספת
        # שטח — הוא יכול להיות מעלית או שיפוץ. הראיה אומרת שהיה היתר, לא כמה
        # מ״ר הוא הוסיף, ולכן הניסוח אינו קובע יותר ממה שהיא יודעת.
        why += (" · בתיק יש היתר שניתן אחרי 18.5.2005 ושטחו אינו ידוע — "
                "אם הוסיף שטח, יש להחריג אותו מהבסיס, וייתכן שהתקרה כאן מנופחת")
    elif post_2005 is None:
        why += " · לא נבדק אם הותרה תוספת אחרי 18.5.2005 — התקרה עשויה להיות מנופחת"
    return base * 4, why


def _is_area(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def cap_400_reliable(post_2005: float | bool | None) -> bool:
    """התקרה מהימנה רק אם ההחרגה של §70ב(א)(1)(ב) נבדקה והוכרעה."""
    return post_2005 is False or _is_area(post_2005)
