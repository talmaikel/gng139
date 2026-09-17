"""בניין שכבר חודש, או שכבר בפרויקט חתום — רשימה ידנית וסימנים. (W5 · #110)

שכבת המבנים מראה את הבניין **הישן**: הניצנים 6 נבנה מחדש לתשע קומות
ורשום אצלנו בשתיים (#101). ותיק הבניין אינו מציג את תיאור הבקשה אלא רק את
״הארוע האחרון להצגה״, ולכן חיפוש ״תמ״א 38״ בו כמעט לא תפס דבר.

החלטת בועז, 16.09: בניין שנראה מחודש **אינו נמסר ואינו מחויב**. הצוות רואה
אותו במסך המנהל ומאשר או פוסל. בניין שאומת כמחודש אינו נכנס לסריקה.

שלושה מצבים:

  ``verified_renewed`` — אומת ידנית. נפסל.
  ``suspected``        — חשד. לא נמסר, ממתין לצוות.
  ``none``             — לא נמצא סימן. **לא נבדק בשטח**, והנוסח אומר את זה.

ומצב רביעי שאינו נכתב: ``unknown`` — אין היתרי תיק לבדוק מולם.

המודול טהור: אין כאן מסד ואין רשת. הכתיבה ב-`renewal.py`.
"""
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

MANUAL_FILE = Path(__file__).resolve().parent / "data" / "verified_renewed.json"
STATUSES = ("verified_renewed", "suspected", "none")
MANUAL_STATUSES = ("verified_renewed", "suspected")
ENTRY_KEYS = {"block", "parcel", "address", "status", "source", "evidence_url",
              "checked_by", "checked_at", "note"}

CUTOFF_2005 = date(2005, 5, 18)     # §70ב(א)(1)(ב)
MIN_FLOORS = 6
MIN_BUILT_RATIO = 2.5               # שטח ברוטו בשכבה / שטח המגרש


def _check(entry: dict[str, Any]) -> dict[str, Any]:
    """רשומה שבורה נופלת בטעינה, ולא נקראת בשקט כ״אין חשד״."""
    key = f'{entry.get("block")}/{entry.get("parcel")}'
    if set(entry) != ENTRY_KEYS:
        raise ValueError(f"{key}: שדות {sorted(set(entry) ^ ENTRY_KEYS)}")
    if entry["status"] not in MANUAL_STATUSES:
        raise ValueError(f'{key}: סטטוס {entry["status"]!r}')
    if not entry["source"]:
        raise ValueError(f"{key}: אין מקור")
    if entry["checked_at"]:
        date.fromisoformat(entry["checked_at"])
    return entry


def load_manual(path: Path = MANUAL_FILE) -> dict[str, dict[str, Any]]:
    """הרשימה הידנית לפי ״גוש/חלקה״."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for e in rows:
        key = f'{_check(e)["block"]}/{e["parcel"]}'
        if key in out:
            raise ValueError(f"{key} מופיעה פעמיים")
        out[key] = e
    return out


@lru_cache(maxsize=1)
def _manual() -> dict[str, dict[str, Any]]:
    return load_manual()


def manual_entry(block: str | None, parcel: str | None) -> dict[str, Any] | None:
    return _manual().get(f"{block}/{parcel}")


def signals(*, post_2005_permit: bool | None, floors: float | None,
            built_sqm: float | None, lot_sqm: float | None,
            representative_event: bool | None = None,
            tama38_event: bool | None = None) -> dict[str, Any]:
    """חשד מתוך מה שכבר נקרא. היתר אחרי 18.5.2005 **וגם** אחד מהשלושה.

    ‏`tama38_event` עומד לבדו: בקשה בתיק שמזכירה תמ״א 38 — בארוע האחרון,
    בסוגה או במהותה — היא סימן חיובי אמיתי גם כשהיעדרו אינו אומר דבר.
    """
    reasons = []
    if tama38_event:
        reasons.append("בקשה בתיק הבניין מזכירה תמ״א 38 או חיזוק")

    ratio = built_sqm / lot_sqm if built_sqm and lot_sqm else None
    if post_2005_permit:
        extra = []
        if floors is not None and floors >= MIN_FLOORS:
            extra.append(f"{floors:g} קומות בשכבת המבנים")
        if ratio is not None and ratio >= MIN_BUILT_RATIO:
            extra.append(f"יחס בנוי/מגרש {ratio:.1f}")
        if representative_event:
            extra.append("ארוע בבקשה מזכיר מייצג")
        if extra:
            reasons += ["היתר שניתן אחרי 18.5.2005", *extra]

    if reasons:
        return {"status": "suspected", "reasons": reasons}
    # ״לא נמצא״ רק כשבאמת היה מה לבדוק
    if post_2005_permit is None or (post_2005_permit and floors is None and ratio is None):
        return {"status": "unknown", "reasons": []}
    return {"status": "none", "reasons": []}


def manual_reasons(entry: dict[str, Any]) -> list[str]:
    out = [f'רשימה ידנית: {entry["source"]}']
    if entry.get("note"):
        out.append(entry["note"])
    if entry.get("checked_by"):
        out.append(f'נבדק ע״י {entry["checked_by"]}' +
                   (f' ב-{entry["checked_at"]}' if entry.get("checked_at") else ""))
    return out


# ‏W5 · 16.09 · חיפוש אינטרנט אוטומטי (`renewal_search.py`) מבטל את הדרישה
# הקודמת ל-Street View ולאישור צוות: חלקה חדשה נבדקת אוטומטית בלבד, ותוצאה
# ודאית פוסלת מיד. הסטטוסים שהחיפוש יכול להחזיר — לא מוכרעים כאן, רק משולבים.
SEARCH_STATUSES = ("verified_renewed", "no_automated_renewal_signal", "unknown", "retryable")


def combine_with_search(signal: dict[str, Any], search: dict[str, Any] | None) -> dict[str, Any]:
    """משלב את `renewal_web_search` (חיפוש רשת אוטומטי) עם חשד הסימנים.

    תוצאה ודאית מהחיפוש פוסלת מיד — גם כשהסימנים אמרו ״לא נמצא״ וגם בלי
    היתר תיק בכלל (החיפוש הוא מקור עצמאי). בדיקה שלא הסתיימה (`retryable`,
    או `unknown` — המפתח חסר) אינה מאפשרת ״עבר״: אם הסימנים היו נותנים
    ‏"none" היא מורידה אותם ל-"unknown", כדי שהמסירה תיחסם עד הרצה חוזרת
    ולא תיקרא כאילו הבדיקה כן נעשתה ולא מצאה דבר. חשד מהסימנים עצמם
    (התהליך הישן, שממתין לצוות) אינו מושפע מבדיקה שלא הסתיימה — הוא כבר
    חוסם מסירה בעצמו.
    """
    if search is None:
        return dict(signal)
    if search.get("status") == "verified_renewed":
        return {"status": "verified_renewed",
                "reasons": [r for r in (search.get("reason"),) if r] + list(signal.get("reasons") or [])}
    if search.get("status") in ("unknown", "retryable") and signal["status"] not in (
            "suspected", "verified_renewed"):
        return {"status": "unknown", "reasons": list(signal.get("reasons") or [])}
    return dict(signal)


def decide(entry: dict[str, Any] | None, signal: dict[str, Any],
          search: dict[str, Any] | None = None) -> dict[str, Any]:
    """הרשימה הידנית גוברת על הכול. אחריה — תוצאת החיפוש האוטומטי, ואז הסימנים.

    ‏`search` אופציונלי (ברירת מחדל `None`) כדי שקוד קיים שקורא ל-`decide`
    בלי הפרמטר הזה ימשיך לעבוד בדיוק כפי שעבד.
    """
    if entry is not None:
        return {"status": entry["status"], "manual": True,
                "reasons": manual_reasons(entry) + list(signal.get("reasons") or [])}
    return {**combine_with_search(signal, search), "manual": False}
