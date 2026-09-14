"""‏B11 · ההשבחה — סף, ואומדן, ובעיקר הפער ביניהם.

שני חישובים שונים, ובכוונה לא אחד:

**הסף** (`breakeven_betterment`) — ההשבחה שמאפסת את הרווח. אינו מוסיף אף
הנחה: כל שאר הקלטים ידועים, והוא נגזר מהם. נפתר נומרית ולא בנוסחה, כי
‏`profit(0) / rate` שוגה בכ-1.5% — ההיטל גורר אחריו עלויות נגזרות.

**האומדן** (`betterment_from_land_values`) — השיטה שחברות יזמיות מריצות
בשלב הראשוני: שווי המצב החדש פחות שווי המצב הקיים. פשוטה חשבונית
ו**שברירית מספרית**, ולכן היא מוצגת עם רגישותה ולא כמספר יחיד.

ומעל שתיהן ההיפוך שהופך את האומדן לשימושי בלי מקדם שאין לנו:
‏`breakeven_land_value_per_right` מתרגם את הסף ל**שווי מ״ר זכויות** —
מספר אחד, שיזם או שמאי שופטים בשנייה.
"""
from dataclasses import dataclass, field
from typing import Callable

# ‏1,526.65 מ״ר קיים × 26,000, מול 4,199 מ״ר חדש × 12,000 — חישוב
# ההתייחסות שהתקבל מחברה יזמית. **שני המספרים אינם מחירי דירות:**
# ‏26,000 הוא שווי הנכס כפי שהוא, לכל מ״ר בנוי קיים; ‏12,000 הוא רכיב
# הקרקע לכל מ״ר זכויות — לפני שבונים עליו. ההפרש ביניהם הוא בדיוק עלות
# הבנייה, העלויות הנלוות והרווח היזמי.
REFERENCE = {
    "existing_area_sqm": 1_526.65, "existing_value_per_sqm_ils": 26_000.0,
    "new_rights_sqm": 4_199.0, "new_rights_with_mamad_sqm": 4_763.0,
    "land_value_per_right_ils": 12_000.0,
    "betterment_ils": 10_695_100.0, "levy_ils": 2_673_775.0,
}


@dataclass
class BettermentEstimate:
    betterment_ils: float
    before_ils: float
    after_ils: float
    new_rights_sqm: float
    notes: list[str] = field(default_factory=list)

    def levy(self, rate: float) -> float:
        # השבחה שלילית אינה מזכה בהחזר — היא פשוט אינה השבחה.
        return max(self.betterment_ils, 0.0) * rate


def betterment_from_land_values(
    *,
    existing_area_sqm: float,
    existing_value_per_sqm_ils: float,
    new_rights_sqm: float,
    land_value_per_right_ils: float,
) -> BettermentEstimate:
    """שווי המצב החדש פחות שווי המצב הקיים.

    ‏**המצב הקיים מוערך כשווי הנכס כפי שהוא** — קרקע ובניין יחד — וזהו
    הקירוב המקובל לשווי הקרקע בזכויות הקיימות. הוא קירוב: ככל שהבניין
    הקיים ישן וקרוב לסוף חייו, השניים מתרחקים זה מזה.
    """
    before = existing_area_sqm * existing_value_per_sqm_ils
    after = new_rights_sqm * land_value_per_right_ils
    return BettermentEstimate(
        betterment_ils=after - before, before_ils=before, after_ils=after,
        new_rights_sqm=new_rights_sqm,
        notes=["שווי המצב הקיים הוא שווי הנכס כפי שהוא — קירוב מקובל "
               "לשווי הקרקע בזכויות הקיימות, ולא שומה"])


def breakeven_betterment(profit_at: Callable[[float], float],
                         *, rate: float, iterations: int = 60) -> float | None:
    """ההשבחה שמאפסת את הרווח, או `None` כשאין רווח גם בהשבחה אפס.

    ‏`None` אינו כישלון אלא ממצא: **אין שיעור השבחה שהופך את הפרויקט
    לכדאי.** הבעיה שם אינה ההיטל.
    """
    lo = 0.0
    base_profit = profit_at(0.0)
    if base_profit <= 0:
        return None
    hi = base_profit / rate * 1.5
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if profit_at(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def breakeven_land_value_per_right(
    breakeven_betterment_ils: float | None,
    *,
    existing_area_sqm: float | None,
    existing_value_per_sqm_ils: float | None,
    new_rights_sqm: float | None,
) -> float | None:
    """הסף, מתורגם למקדם היחיד שאיננו יודעים.

    **זה מה שהופך את השיטה לשימושית בלי שמאי.** באומדן היזמי יש מקדם
    אחד שאין לנו — שווי מ״ר זכויות — וכל השאר ידוע לנו. במקום לנחש
    אותו, מחשבים את הערך שבו הפרויקט מתאפס:

        סף_השבחה = מ״ר_חדש × c − מ״ר_קיים × שווי_קיים
        c* = (סף_השבחה + מ״ר_קיים × שווי_קיים) / מ״ר_חדש

    ‏*״הפרויקט כדאי כל עוד מ״ר זכויות באזור שווה פחות מ-c*.״* יזם שמכיר
    את השוק שלו שופט את זה מיד; הוא אינו יכול לשפוט ״השבחה של 229
    מיליון״.
    """
    if (breakeven_betterment_ils is None or not new_rights_sqm
            or existing_area_sqm is None or existing_value_per_sqm_ils is None):
        return None
    before = existing_area_sqm * existing_value_per_sqm_ils
    return (breakeven_betterment_ils + before) / new_rights_sqm


def sensitivity(estimate_fn: Callable[[float, float], float],
                existing_value: float, land_value: float,
                *, step: float = 0.10) -> dict[str, float]:
    """כמה זז ההיטל כששני המקדמים זזים ב-10%.

    **זה הממצא המרכזי על השיטה הזו.** היא הפרש בין שני מספרים גדולים,
    ולכן טעות קטנה בכל אחד מהם מתפוצצת בתוצאה. בחישוב ההתייחסות: ‏10%
    בשווי מ״ר הזכויות מזיזים את ההיטל ב-47%.
    """
    base = estimate_fn(existing_value, land_value)
    return {
        "base_ils": base,
        "land_value_up_ils": estimate_fn(existing_value, land_value * (1 + step)),
        "land_value_down_ils": estimate_fn(existing_value, land_value * (1 - step)),
        "existing_value_up_ils": estimate_fn(existing_value * (1 + step), land_value),
        "existing_value_down_ils": estimate_fn(existing_value * (1 - step), land_value),
    }
