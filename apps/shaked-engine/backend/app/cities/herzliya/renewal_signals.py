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

    ‏`tama38_event` עומד לבדו: ארוע אחרון שמזכיר תמ״א 38 הוא סימן חיובי
    אמיתי גם כשהיעדרו אינו אומר דבר.
    """
    reasons = []
    if tama38_event:
        reasons.append("ארוע אחרון בבקשה בתיק מזכיר תמ״א 38 או חיזוק")

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


def decide(entry: dict[str, Any] | None, signal: dict[str, Any]) -> dict[str, Any]:
    """הרשימה הידנית גוברת על הסימנים. הסימנים נשארים בנימוק."""
    if entry is None:
        return {**signal, "manual": False}
    return {"status": entry["status"], "manual": True,
            "reasons": manual_reasons(entry) + list(signal.get("reasons") or [])}
