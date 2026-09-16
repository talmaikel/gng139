"""שטח לפי מדיניות הרצליה — כמה מתקרת ה-400% נכנס בפועל בתוך קווי הבניין. (W1, #106)

‏**400% הוא תקרה בחוק ולא זכות** (§70ב: ״לא יעלה על״), והוועדה רשאית לקבוע
פחות (מדיניות §2ה). מה שנבנה בפועל מוגבל במספר הקומות לפי רוחב הרחוב
(§5, עמ׳ 8), בנסיגות בקומות העליונות (אותה טבלה), ובקווי הבניין (§6, עמ׳ 10;
§7, עמ׳ 12). הגרסה הקודמת של התיק חישבה את הרווח על כל התקרה, וסייג R1
השווה את שטח הקומה ל-100% מהמגרש — אבל קומה בתוך קווי הבניין היא רק כמחצית
מהמגרש (#78).

**מה שהמודול יודע ומה לא — ולכן התוצאה תמיד אומדן:**

* **איזו צלע היא החזית אינו ידוע.** אין בנתונים גאומטריה של הרחוב, רק כמה
  חזיתות יש (`frontages_v2`). לכן החלקה מסובבת אל המלבן החוסם הקטן ביותר,
  ונבדקים כל הכיוונים: נמוך = הכיוון הגרוע, גבוה = הטוב.
* **קו בניין קדמי 5 מ׳ הוא ברירת מחדל שמרנית, לא כלל מדיניות.** המדיניות
  קובעת אותו ״בהתאם לקווי הבנייה הקיימים ברחוב״ (§7), ומציגה קווים של 4
  ו-5 מ׳. כשאין מדידה, 5 מ׳ הוא הבסיס והנמוך ו-4 מ׳ הוא גבול עליון בלבד.
* **‏η = 0.9 הוא אומדן תכנוני, לא שטח סטטוטורי.** לכן הפלט מפריד בין
  המעטפת הגאומטרית המלאה לבין האומדן השמרני שעליו רץ התרחיש הכלכלי.
* **אין קומת גג מעל המקסימום.** מספר הקומות בטבלה כולל קומת קרקע (הערה 1),
  וגובה הבניין בטבלת קווי הבניין הוא ברוטו כולל קומת הגג (§6 הערה 1).
* **מרפסות אינן כאן.** הן בנוסף לשטח (§2ו) ובולטות מעבר לקווים.

פונקציה טהורה: בלי מסד ובלי רשת. הקורא מביא פוליגון ב-ITM.
"""
from dataclasses import dataclass, field
from math import atan2, degrees

import numpy as np
from shapely import affinity
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from app.cities.herzliya.rights import POLICY_URL

ETA = 0.9
FRONT_LINE_FALLBACK_M = 5.0
FRONT_LINE_UPPER_M = 4.0
SETBACK_M = 3.0
SMALL_LOT_SQM = 750.0

# ‏§6, עמ׳ 10 · קווי בניין לפי גובה הבניין (ברוטו). (צד נמוך, צד גבוה, אחורי)
# ‏״עד 6 קומות: 3–3.5 מ׳״ — הטווח עצמו נכנס לנמוך/גבוה.
# ‏הערה 5: במגרש קטן מ-750 מ״ר ניתן לבחון צד קטן מ-4 אך לא פחות מ-3.5.
def _lines(floors: float, lot_sqm: float | None) -> tuple[float, float, float]:
    if floors <= 6:
        return 3.5, 3.0, 5.0
    side_high = 3.5 if lot_sqm is not None and lot_sqm < SMALL_LOT_SQM else 4.0
    return 4.0, side_high, 6.0 if floors >= 10 else 5.0


# ‏§5, עמ׳ 8 · נסיגות לפי מספר הקומות המרבי. לכל קומה: (נסיגה קדמית, נסיגה אחורית),
# מצטברות — ״הנסיגות תחלנה מקו התכסית של הקומה שמתחתיה״.
#   9–10 מ׳ → 7 קומות: 6 בלי נסיגה, 3 מ׳ לקדמית ולאחורית בקומה 7.
#   10–12 מ׳ → 8 קומות: 6 בלי נסיגה, 3 מ׳ לקדמית בקומות 7 ו-8, ולאחורית בקומה 8.
#   12–15 מ׳ → 9 קומות: 7 בלי נסיגה, 3 מ׳ לקדמית בקומות 8 ו-9, ולאחורית בקומה 9.
# מעל 15 מ׳ הטבלה מפנה לבחינה נקודתית; תקרת קטגוריה של 9 מקבלת את שורת 12–15.
def setbacks(floors: float) -> list[tuple[float, float, float]] | None:
    """(משקל, נסיגה קדמית מצטברת, נסיגה אחורית מצטברת) לכל קומה, מלמטה."""
    if floors <= 6:
        whole = int(floors)
        out = [(1.0, 0.0, 0.0)] * whole
        if floors > whole:                      # ‏5.5 = חמש קומות ומחצית קומה
            out.append((floors - whole, 0.0, 0.0))
        return out
    s = SETBACK_M
    if floors == 7:
        return [(1.0, 0.0, 0.0)] * 6 + [(1.0, s, s)]
    if floors == 8:
        return [(1.0, 0.0, 0.0)] * 6 + [(1.0, s, 0.0), (1.0, 2 * s, s)]
    if floors == 9:
        return [(1.0, 0.0, 0.0)] * 7 + [(1.0, s, 0.0), (1.0, 2 * s, s)]
    return None


@dataclass
class Layout:
    """אילו צלעות של המלבן החוסם הן חזיתות ואילו מקבלות קו אחורי."""
    fronts: tuple[str, ...]
    rears: tuple[str, ...]


SIDES = ("x0", "x1", "y0", "y1")
OPPOSITE = {"x0": "x1", "x1": "x0", "y0": "y1", "y1": "y0"}


def layouts(frontages: int | None) -> dict[str, list[Layout]]:
    """מצבי החזית לבדיקה. חזית אחת: 4 כיוונים. פינתי: זוגות צלעות סמוכות.

    במגרש פינתי המסמך אינו קובע איזו משתי הצלעות הפנימיות היא אחורית.
    הבסיס והגבוה בודקים את שתי הפרשנויות. הנמוך מיישם את החיתוך השמרני
    שלהן: שתי הצלעות הפנימיות מקבלות את הקו האחורי הגדול יותר.

    כשמספר החזיתות אינו ידוע, הנמוך נבדק גם כפינתי והגבוה גם כחזית אחת.
    """
    single = [Layout((f,), (OPPOSITE[f],)) for f in SIDES]
    pairs = [(a, b) for a in ("x0", "x1") for b in ("y0", "y1")]
    corner_safe = [Layout((a, b), (OPPOSITE[a], OPPOSITE[b])) for a, b in pairs]
    corner_options = [layout for a, b in pairs for layout in (
        Layout((a, b), (OPPOSITE[a],)),
        Layout((a, b), (OPPOSITE[b],)),
    )]
    if frontages is None:
        return {"low": single + corner_safe, "base": single, "high": single + corner_options}
    if frontages >= 2:
        return {"low": corner_safe, "base": corner_options, "high": corner_options}
    return {"low": single, "base": single, "high": single}


def _frame(parcel: BaseGeometry) -> BaseGeometry:
    """החלקה מסובבת כך שהמלבן החוסם הקטן ביותר שלה מקביל לצירים."""
    # מלבן מקביל לצירים הוא מקרה מנוון לחישוב, ו-shapely מזהיר על חלוקה באפס.
    with np.errstate(divide="ignore", invalid="ignore"):
        rect = parcel.minimum_rotated_rectangle
    (x0, y0), (x1, y1) = list(rect.exterior.coords)[:2]
    angle = degrees(atan2(y1 - y0, x1 - x0))
    return affinity.rotate(parcel, -angle, origin=parcel.centroid)


def _plate(frame: BaseGeometry, core: BaseGeometry, layout: Layout,
           front: float, side: float, rear: float, f_back: float, r_back: float) -> float:
    minx, miny, maxx, maxy = frame.bounds
    margin = {s: side for s in SIDES}
    for s in layout.fronts:
        margin[s] = front + f_back
    for s in layout.rears:
        margin[s] = max(margin[s], rear + r_back)
    clip = (minx + margin["x0"], miny + margin["y0"], maxx - margin["x1"], maxy - margin["y1"])
    if clip[0] >= clip[2] or clip[1] >= clip[3]:
        return 0.0
    return core.intersection(box(*clip)).area


def _total(frame, lot_sqm, floors, layout, side_choice: str,
           front_line_m: float) -> tuple[float, float]:
    """(סך שטח הקומות, שטח הקומה הטיפוסית) לכיוון אחד."""
    side_low, side_high, rear = _lines(floors, lot_sqm)
    side = side_low if side_choice == "low" else side_high
    # ‏כל נקודה במעטפת רחוקה לפחות קו הצד מכל גבול — כך צלע לא ישרה אינה נחתכת רק לאורך המלבן.
    core = frame.buffer(-side, join_style=2)
    if core.is_empty:
        return 0.0, 0.0
    steps = setbacks(floors)
    total, typical = 0.0, None
    for weight, f_back, r_back in steps:
        area = _plate(frame, core, layout, front_line_m, side, rear, f_back, r_back)
        typical = area if typical is None else typical
        total += weight * area
    return total, typical or 0.0


@dataclass
class PolicyArea:
    plot_sqm: float
    cap_400_sqm: float | None
    envelope_sqm: float                 # קומה טיפוסית בתוך קווי הבניין, אומדן בסיס
    low_sqm: float
    base_sqm: float
    high_sqm: float
    geometric_low_sqm: float
    geometric_base_sqm: float
    geometric_high_sqm: float
    front_lines_m: dict[str, float]
    floors_low: float
    floors_high: float
    corner: bool | None
    binding: str                        # envelope | cap
    limits: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def far(self, sqm: float | None) -> float | None:
        """אחוזי בנייה: שטח בנוי חלקי שטח המגרש."""
        return sqm / self.plot_sqm * 100 if sqm is not None and self.plot_sqm else None

    def as_dict(self) -> dict:
        """‏**400% בחוק הוא פי ארבעה מהשטח הבנוי הקיים (§70ב), ולא משטח המגרש.**
        לכן התקרה מוצגת גם במ״ר וגם כאחוזי בנייה מהמגרש, והפער נמדד בשניהם."""
        cap = self.cap_400_sqm
        cap_far = self.far(cap)

        def area_case(sqm: float) -> dict:
            far = self.far(sqm)
            return {
                "sqm": round(sqm, 1),
                "far_pct": round(far, 1) if far is not None else None,
                "share_of_cap": round(sqm / cap, 3) if cap else None,
                "gap_sqm": round(cap - sqm, 1) if cap else None,
                "gap_far_pct": round(cap_far - far, 1) if cap_far and far is not None else None,
                "unrealizable_share": round(1 - sqm / cap, 3) if cap else None,
            }

        out = {
            "plot_sqm": round(self.plot_sqm, 1),
            "envelope_sqm": round(self.envelope_sqm, 1),
            "envelope_share_of_plot": round(self.envelope_sqm / self.plot_sqm, 3) if self.plot_sqm else None,
            "cap_400_sqm": round(cap, 1) if cap else None,
            "cap_400_far_pct": round(cap_far, 1) if cap_far else None,
            "floors": {"low": self.floors_low, "high": self.floors_high},
            "corner": self.corner,
            "binding": self.binding,
            "certainty": "estimate",
            "eta": ETA,
            "front_lines_m": self.front_lines_m,
            "limits": self.limits,
            "assumptions": self.assumptions,
            "sources": [{"label": "מדיניות חלופת שקד הרצליה, אפריל 2026 · §5 עמ׳ 8 · §6 עמ׳ 10 · §7 עמ׳ 12",
                         "url": POLICY_URL}],
        }
        for name, sqm in (("low", self.low_sqm), ("base", self.base_sqm), ("high", self.high_sqm)):
            out[name] = area_case(sqm)
        out["geometric"] = {
            name: area_case(sqm) for name, sqm in (
                ("low", self.geometric_low_sqm),
                ("base", self.geometric_base_sqm),
                ("high", self.geometric_high_sqm),
            )
        }
        return out


def compute(parcel_itm: BaseGeometry | None, *, plot_sqm: float | None,
            floors_low: float | None, floors_high: float | None,
            cap_400_sqm: float | None, frontages: int | None,
            front_line_m: float | None = None) -> tuple[PolicyArea | None, str | None]:
    """השטח שמותר לבנות לפי המדיניות. מחזיר (תוצאה, None) או (None, למה לא)."""
    if parcel_itm is None or parcel_itm.is_empty:
        return None, "אין פוליגון לחלקה"
    if floors_low is None:
        return None, "מספר הקומות לפי המדיניות אינו ידוע (רוחב רחוב או קטגוריה) — אי אפשר לחשב מעטפת"
    floors_high = floors_high or floors_low
    if setbacks(floors_low) is None or setbacks(floors_high) is None:
        return None, f"אין בטבלת המדיניות דפוס נסיגות ל-{floors_low:g}–{floors_high:g} קומות"
    plot = plot_sqm or parcel_itm.area
    frame = _frame(parcel_itm)
    options = layouts(frontages)
    front_lines = ({"low": front_line_m, "base": front_line_m, "high": front_line_m}
                   if front_line_m is not None else
                   {"low": FRONT_LINE_FALLBACK_M, "base": FRONT_LINE_FALLBACK_M,
                    "high": FRONT_LINE_UPPER_M})

    def totals(floors, which, side_choice):
        return [_total(frame, plot, floors, lay, side_choice, front_lines[which])
                for lay in options[which]]

    low_runs = totals(floors_low, "low", "low")
    base_runs = totals(floors_low, "base", "low")
    high_runs = totals(floors_high, "high", "high")
    low = min(t for t, _ in low_runs)
    base = sum(t for t, _ in base_runs) / len(base_runs)
    high = max(t for t, _ in high_runs)
    envelope = sum(p for _, p in base_runs) / len(base_runs)

    def capped(sqm, factor=1.0):
        v = factor * sqm
        return min(v, cap_400_sqm) if cap_400_sqm else v

    geometric_low, geometric_base, geometric_high = capped(low), capped(base), capped(high)
    low_s, base_s, high_s = capped(low, ETA), capped(base, ETA), capped(high, ETA)
    binding = "cap" if cap_400_sqm and ETA * base >= cap_400_sqm else "envelope"

    side_low, side_high, rear = _lines(floors_low, plot)
    corner = None if frontages is None else frontages >= 2
    span = f"{floors_low:g}" if floors_low == floors_high else f"{floors_low:g}–{floors_high:g}"
    limits = [f"{span} קומות לפי רוחב הרחוב וקטגוריית המדיניות (§5, עמ׳ 8), כולל קומת קרקע, בלי קומת גג",
              f"קווי בניין: קדמי {front_lines['base']:g} מ׳ כברירת מחדל, צד {side_low:g} מ׳, אחורי {rear:g} מ׳ (§6–7, עמ׳ 10–12)"]
    if max(floors_low, floors_high) > 6:
        limits.append("נסיגה של 3 מ׳ בקומות העליונות לחזית הקדמית, ובקומה העליונה גם לאחורית (§5)")
    if corner:
        limits.append("מגרש פינתי: שתי חזיתות; בנמוך שתי הצלעות הפנימיות מקבלות קו אחורי שמרני")
    limits.append(f"קומה טיפוסית בתוך הקווים: כ-{envelope:,.0f} מ״ר, {envelope / plot:.0%} מהמגרש")
    if binding == "cap":
        limits.append("המעטפת גדולה מתקרת ה-400%, ולכן התקרה היא המגבלה")

    assumptions = [
        (f"קו בניין קדמי {front_line_m:g} מ׳ — התקבל כקלט"
         if front_line_m is not None else
         "קו בניין קדמי לא נמדד — 5 מ׳ הוא בסיס שמרני; 4 מ׳ מופיע רק בגבול העליון; המדיניות קובעת לפי קווי הבנייה ברחוב (§7)"),
        "צלע החזית אינה ידועה — נבדקו כל הכיוונים של המלבן החוסם: נמוך = הגרוע, גבוה = הטוב",
        f"η = {ETA:g}: אומדן תכנוני שמרני; המעטפת הגאומטרית ללא המקדם מוצגת בנפרד",
        "מרפסות אינן בשטח (§2ו) · שטח ציבורי בנוי (§2ז) לא נוכה · הוועדה רשאית לקבוע פחות (§2ה)",
    ]
    if corner:
        assumptions.append("זהות הקו האחורי במגרש פינתי אינה מפורשת במדיניות — הטווח כולל את שתי הפרשנויות")
    if corner is None:
        assumptions.append("מספר החזיתות אינו ידוע — הנמוך נבדק גם כמגרש פינתי")
    return PolicyArea(plot_sqm=plot, cap_400_sqm=cap_400_sqm, envelope_sqm=envelope,
                      low_sqm=low_s, base_sqm=base_s, high_sqm=high_s,
                      geometric_low_sqm=geometric_low, geometric_base_sqm=geometric_base,
                      geometric_high_sqm=geometric_high, front_lines_m=front_lines,
                      floors_low=floors_low, floors_high=floors_high, corner=corner,
                      binding=binding, limits=limits, assumptions=assumptions), None
