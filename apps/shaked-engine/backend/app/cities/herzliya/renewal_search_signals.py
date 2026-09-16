"""‏W5 · חיפוש אינטרנט אוטומטי לאיתור בניין שכבר חודש — הלוגיקה הטהורה.

אין כאן רשת ואין מסד: נרמול כתובת, וסיווג תוצאות חיפוש (title/description/url
בלבד — לא נכנסים לעמוד ולא סורקים אותו) מול מילות מפתח של תמ״א 38 /
התחדשות עירונית. הקריאה לספק החיפוש ב-`renewal_search_provider.py`,
והכתיבה למסד וההרצה האוטומטית (backfill) ב-`renewal_search.py` — לפי אותו
עיקרון הפרדה שכבר קיים כאן בין `archive_client.py` (רשת) ובין
`renewal_signals.py` (לוגיקה טהורה).

התאמת כתובת דורשת שלושה דברים יחד: אותו שם רחוב אחרי נרמול, אותו מספר בית
(או בתוך טווח, למשל "יגאל אלון 4-8"), ואותה עיר. התאמת שם רחוב בלבד אינה
מספיקה — היא בדיוק מה שהיה מזהה "יגאל אלון 2" כתוצאה על "יגאל אלון 6".

מילת מפתח מזכה בפסילה רק כשאין ניסוח שולל (״לא במסגרת תמ״א 38״, ״אינו
פרויקט תמ״א״, ״ללא תמ״א 38״) בסמוך לפניה.
"""
import re
from dataclasses import dataclass

# מילות התחדשות/תמ״א שמזכות בפסילה אוטומטית. הסדר קובע איזה תג יידווח
# כשיש כמה התאמות — הכי ספציפי קודם (38/1, 38/2) לפני הכללי (38 בלבד).
DISQUALIFYING_KEYWORDS: tuple[str, ...] = (
    'תמ"א 38/1',
    'תמ"א 38/2',
    'תמ"א 38',
    "תמא 38",
    "חיזוק ותוספת",
    "הריסה ובנייה",
    "הריסה ובניה",
    "התחדשות עירונית",
    'פרויקט תמ"א',
)

# עמוד פרויקט במדלן הוא סימן חיובי כשלעצמו, גם בלי אחת ממילות המפתח בטקסט.
MADLAN_PROJECT_MARKER = "madlan.co.il/projects"
MADLAN_PROJECT_LABEL = "מודעת פרויקט התחדשות במדלן"

# ניסוח שולל בסמוך למילת המפתח מבטל את הפסילה. ‏\b עובד גם על עברית: ‏re
# מתייחס לאות עברית כתו-מילה תחת יוניקוד, שהוא ברירת המחדל למחרוזת ב-Python 3.
_NEGATION = re.compile(r"\b(לא|אינו|אינה|אין|ללא|בלי)\b")
_NEGATION_WINDOW = 20  # תווים לפני תחילת ההתאמה שנבדקים לניסוח שולל

_GERESH_MAP = str.maketrans({
    "״": '"', "׳": "'",  # gershayim, geresh
    "”": '"', "“": '"',  # curly double quotes
    "’": "'", "‘": "'",  # curly single quotes
})
_STREET_PREFIX = re.compile(r"^\s*(רח['׳]|רחוב)\s+")
_LEADING_NUMBER = re.compile(r"^(\d+)")
_NUMBER_OR_RANGE = re.compile(r"(\d+)\s*(?:[-‐-―]\s*(\d+))?")


def _normalize_text(text: str | None) -> str:
    """רווחים לרווח יחיד, וגרשיים לצורתם הרגילה — לא יותר. שם הרחוב עצמו לא נשבר."""
    s = (text or "").translate(_GERESH_MAP)
    return re.sub(r"\s+", " ", s).strip()


@dataclass(frozen=True)
class NormalizedAddress:
    street: str
    house_number: int | None
    house_number_raw: str
    city: str

    @property
    def display(self) -> str:
        parts = [p for p in (f"{self.street} {self.house_number_raw}".strip(), self.city) if p]
        return ", ".join(parts)


def normalize_address(street: str, house_number: str | int, city: str) -> NormalizedAddress:
    """שם הרחוב, מספר הבית והעיר — מנורמלים להשוואה, לא לתצוגה."""
    street_n = _STREET_PREFIX.sub("", _normalize_text(street))
    city_n = _normalize_text(city)
    raw = str(house_number).strip()
    m = _LEADING_NUMBER.match(raw)
    number = int(m.group(1)) if m else None
    return NormalizedAddress(street=street_n, house_number=number, house_number_raw=raw, city=city_n)


@dataclass(frozen=True)
class ClassificationOutcome:
    status: str  # "verified_renewed" | "no_automated_renewal_signal"
    matched_keyword: str | None = None
    result_title: str | None = None
    result_url: str | None = None
    address_match_score: float | None = None
    reason: str | None = None


NO_SIGNAL = ClassificationOutcome(status="no_automated_renewal_signal")


def _address_score(haystack: str, normalized: NormalizedAddress) -> float:
    """0 — אין התאמה. 1 — מספר מדויק. 0.85 — בתוך טווח כתובות."""
    if normalized.house_number is None or not normalized.street:
        return 0.0
    for m in re.finditer(re.escape(normalized.street), haystack):
        tail = haystack[m.end():m.end() + 12].lstrip(" ,.\"'")
        num_m = _NUMBER_OR_RANGE.match(tail)
        if not num_m:
            continue
        lo = int(num_m.group(1))
        hi = int(num_m.group(2)) if num_m.group(2) else lo
        if lo <= normalized.house_number <= hi:
            return 1.0 if lo == hi == normalized.house_number else 0.85
    return 0.0


def _address_matches(result_haystack: str, normalized: NormalizedAddress) -> float:
    """ציון התאמת כתובת: רחוב+מספר (או טווח) **וגם** עיר. 0 אם משהו חסר."""
    score = _address_score(result_haystack, normalized)
    if score <= 0.0:
        return 0.0
    if normalized.city and normalized.city not in result_haystack:
        return 0.0
    return score


def _find_disqualifying_keyword(haystack: str) -> str | None:
    for keyword in DISQUALIFYING_KEYWORDS:
        for m in re.finditer(re.escape(keyword), haystack):
            window = haystack[max(0, m.start() - _NEGATION_WINDOW):m.start()]
            if not _NEGATION.search(window):
                return keyword
    return None


def classify_renewal_result(normalized: NormalizedAddress, results: "list") -> ClassificationOutcome:
    """הראשונה מהתוצאות שהכתובת שלה תואמת **וגם** יש בה מילת פסילה — פוסלת.

    תוצאה שהכתובת בה אינה תואמת אינה נבדקת על מילות מפתח כלל: אחרת "יגאל
    אלון 45" עם תמ״א 38 הייתה פוסלת את "יגאל אלון 6".
    """
    for result in results:
        title = _normalize_text(getattr(result, "title", None))
        description = _normalize_text(getattr(result, "description", None))
        url = getattr(result, "url", None) or ""
        haystack = f"{title} {description} {url}".strip()
        score = _address_matches(haystack, normalized)
        if score <= 0.0:
            continue
        keyword = _find_disqualifying_keyword(f"{title} {description}")
        is_madlan_project = MADLAN_PROJECT_MARKER in url.lower()
        if keyword is None and not is_madlan_project:
            continue
        label = keyword or MADLAN_PROJECT_LABEL
        reason = f"נמצא אוטומטית {label} בכתובת {normalized.display}"
        return ClassificationOutcome(status="verified_renewed", matched_keyword=label,
                                     result_title=getattr(result, "title", None),
                                     result_url=getattr(result, "url", None),
                                     address_match_score=score, reason=reason)
    return NO_SIGNAL
