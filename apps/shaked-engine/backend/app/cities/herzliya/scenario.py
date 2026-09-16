"""‏W8 · תרחיש של היזם: הנתונים שלנו הם ברירת המחדל, והיזם משנה אותם.

שתי בקשות של השותפים (12, 14): *״התמהיל לא בקישור נפרד אלא חלק מהדוח
הכלכלי, כמחשבון — ואחרי שבוחרים תמורה ותמהיל, דוח 0 נגזר מהם״*, ו-*״לתת
ליזם להזין בעצמו שדות בחישוב הכלכלי — הנתונים שלנו כברירת מחדל״*.

**המחשבון אינו מודל שני.** הערכים שהיזם הזין נכנסים לאותה טבלת הנחות,
לאותו ‏`FeasibilityInput` ולאותם ‏`_run` ו-`_betterment` שהתיק מחושב בהם
(``dossier._economics``). כך הרווח אחרי היטל, המשפט ליד הרווח, שורות
העלות וההסבר נגזרים מהבחירה — ולא ממספר שחושב בצד.

**ושום דבר אינו נשמר.** ההזדמנות משותפת לכל החברות שקיבלו אותה, ותמהיל
שנשמר עליה (B15) הופיע בתיק של חברה אחרת.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.economic.schemas import FeasibilityInput
from app.services.unit_mix.optimizer import evaluate_mix, optimize_unit_mix
from app.services.unit_mix.schemas import UnitMixOptimizationInput
from app.services.unit_mix.service import DEFAULT_UNIT_AREAS_SQM, _unit_types

# הסטטוס והמקור של שורה שהיזם שינה — בטבלת ההנחות, באקסל וב-PDF.
DEVELOPER = "developer"
DEVELOPER_SOURCE = "הוזן על ידי היזם"

AREA_BASIS_LABEL = {
    "policy_low": "לפי המדיניות — הקצה הנמוך",
    "policy_base": "לפי המדיניות — אומדן בסיס",
    "policy_high": "לפי המדיניות — הקצה הגבוה",
    "cap_400": "תקרת 400% (תאורטית)",
    "custom": "שטח שהזין היזם",
}

# שדה בבקשה ← שורה בטבלת ההנחות. שדה שאינו כאן אינו שורה בטבלה.
ASSUMPTION_OF = {
    "sale_price_per_sqm": "sale_price_per_sqm_ils",
    "construction_cost_per_sqm": "construction_cost_per_sqm_ils",
    "underground_cost_per_sqm": "underground_cost_per_sqm_ils",
    "tenant_compensation_sqm_per_existing_unit": "tenant_compensation_sqm_per_existing_unit",
    "average_existing_unit_sqm": "average_existing_unit_sqm",
    "developer_profit_target_ratio": "developer_profit_target_ratio",
    "finance_ratio": "finance_ratio",
    "betterment_ils": "betterment_base_ils",
}


class ScenarioRejected(ValueError):
    """תרחיש שאי אפשר לחשב כמו שהוזן — ‏422 עם משפט ליזם."""


class MixRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rooms: Literal[3, 4, 5]
    units: int = Field(ge=0, le=1000)


class ScenarioOverrides(BaseModel):
    """מה שהיזם שינה. כל שדה רשות; שדה שלא נשלח נשאר ברירת המחדל של התיק.

    הטווחים רחבים בכוונה — הם עוצרים הקלדה שגויה (4,200 במקום 42,000 הוא
    עדיין בטווח; 42 אינו), ולא שיקול דעת של יזם.
    """
    model_config = ConfigDict(extra="forbid")

    area_basis: Literal["policy_low", "policy_base", "policy_high", "cap_400", "custom"] | None = None
    custom_area_sqm: float | None = Field(default=None, gt=0, le=500_000)
    sale_price_per_sqm: float | None = Field(default=None, ge=5_000, le=200_000)
    construction_cost_per_sqm: float | None = Field(default=None, ge=1_000, le=50_000)
    underground_cost_per_sqm: float | None = Field(default=None, ge=0, le=50_000)
    tenant_compensation_sqm_per_existing_unit: float | None = Field(default=None, ge=0, le=100)
    average_existing_unit_sqm: float | None = Field(default=None, ge=20, le=500)
    # הצד ה״לפני״ של אומדן ההשבחה — מחיר מ״ר של דירה קיימת ליד החלקה.
    existing_price_per_sqm: float | None = Field(default=None, ge=1_000, le=200_000)
    # השבחה שהיזם קבע (שומה, הערכה משלו). מחליפה את האומדן בשיטת היזם.
    betterment_ils: float | None = Field(default=None, ge=0, le=10_000_000_000)
    developer_profit_target_ratio: float | None = Field(default=None, ge=0, le=1)
    finance_ratio: float | None = Field(default=None, ge=0, le=0.5)
    mix: Literal["optimize"] | list[MixRow] | None = None

    @model_validator(mode="after")
    def _consistent(self):
        if self.area_basis == "custom" and self.custom_area_sqm is None:
            raise ValueError("שטח שהזין היזם דורש custom_area_sqm")
        if self.custom_area_sqm is not None and self.area_basis != "custom":
            raise ValueError("custom_area_sqm נשלח רק עם area_basis=custom")
        if isinstance(self.mix, list):
            rooms = [r.rooms for r in self.mix]
            if len(rooms) != len(set(rooms)):
                raise ValueError("כל מספר חדרים מופיע בתמהיל פעם אחת")
            if not any(r.units for r in self.mix):
                raise ValueError("בתמהיל אין דירות")
        return self


def scenario_mix(inputs: FeasibilityInput, mix: str | list[MixRow], *, missing: list[str],
                 default_compensation: float, existing_unit_label: str | None) -> dict[str, Any]:
    """התמהיל על השטח, המחיר והתמורה של התרחיש — ‏B15, בלי לשמור דבר.

    ‏``"optimize"`` מריץ את האופטימיזציה של B15; רשימה היא תמהיל שהיזם הזין,
    מתומחר באותו חשבון (``evaluate_mix``). תמהיל שאינו נכנס בשטח ליזם נדחה;
    חריגה ממגבלות המדיניות נאמרת ואינה נדחית.

    הדירות הקיימות לפי השטח הממוצע של התרחיש — אותו מספר שבטבלת ההנחות. סך
    שטח הבעלים זהה לחישוב דירה-דירה (n × (ממוצע + תוספת)); מה שהממוצע מטשטש
    הוא כמה מדירות הבעלים בטווח הדירות הקטנות.
    """
    request = UnitMixOptimizationInput(
        existing_unit_areas_sqm=[inputs.average_existing_unit_sqm] * inputs.existing_units,
        buildable_area_sqm=inputs.buildable_area_sqm,
        main_area_ratio=inputs.main_area_ratio,
        economic_input=inputs,
        economic_missing_inputs=missing,
        compensation_sqm_per_existing_unit=inputs.tenant_compensation_sqm_per_existing_unit,
        default_compensation_sqm_per_existing_unit=default_compensation,
        # כל גודל דירה במחיר המכירה של התרחיש (service._unit_types).
        unit_types=_unit_types(inputs.sale_price_per_sqm),
    )
    if mix == "optimize":
        result = optimize_unit_mix(request)
        if not result.candidates:
            reason = next((w for w in reversed(result.warnings) if "אין תמהיל" in w or "אינן נכנסות" in w),
                          "לא נמצא תמהיל שעומד יחד בשטח ליזם ובאילוצי מדיניות הרצליה.")
            raise ScenarioRejected(f"לא נמצא תמהיל מיטבי: {reason}")
        best, policy_warnings, notes = result.candidates[0], [], list(result.warnings)
    else:
        best, policy_warnings = evaluate_mix(request, {f"{r.rooms}r": r.units for r in mix if r.units})
        if best is None:
            raise ScenarioRejected(policy_warnings[0])
        notes = []

    rows = sorted(({"rooms": int(k.removesuffix("r")), "area_sqm": DEFAULT_UNIT_AREAS_SQM[int(k.removesuffix("r"))],
                    "units": n} for k, n in best.counts.items() if n), key=lambda r: r["rooms"])
    parts = " · ".join(f'{r["units"]} × {r["rooms"]} חד׳ ({r["area_sqm"]:,.0f} מ״ר)' for r in rows)
    head = "תמהיל מיטבי ליזם (אומדן)" if mix == "optimize" else "תמהיל שהזין היזם"
    summary = (f"{head}: {parts} — {best.developer_units} דירות ליזם ו-{best.tenant_units} לבעלי הדירות · "
               f"לפי תוספת של {inputs.tenant_compensation_sqm_per_existing_unit:g} מ״ר לכל דירה קיימת "
               f"ושטח דירה קיימת ממוצע של {inputs.average_existing_unit_sqm:,.0f} מ״ר")
    if best.unused_developer_sqm > 0.5:
        summary += (f" · {best.unused_developer_sqm:,.0f} מ״ר מתוך {best.developer_available_sqm:,.0f} ליזם "
                    "לא נכנסים לתמהיל ואינם נמכרים")
    summary += " · הרווח מחושב לפי הדירות שבתמהיל"
    if policy_warnings:
        summary += " · חורג ממדיניות הרצליה: " + " ".join(policy_warnings)
    return {
        "source": "optimize" if mix == "optimize" else DEVELOPER,
        "rows": rows,
        "developer_units": best.developer_units,
        "tenant_units": best.tenant_units,
        "total_units": best.total_new_units,
        "compensation_sqm_per_existing_unit": inputs.tenant_compensation_sqm_per_existing_unit,
        "average_existing_unit_sqm": inputs.average_existing_unit_sqm,
        "average_existing_unit_source": existing_unit_label,
        "sale_price_per_sqm_ils": inputs.sale_price_per_sqm,
        "developer_used_sqm": best.developer_used_sqm,
        "developer_available_sqm": best.developer_available_sqm,
        "unused_developer_sqm": best.unused_developer_sqm,
        "small_unit_share": best.small_unit_share,
        # כולל מע״מ, כמו מחיר המכירה; המחשבון מנכה מע״מ (calculator.py).
        "developer_sale_revenue_ils": best.gross_developer_revenue_ils,
        "policy_warnings": policy_warnings,
        "notes": notes,
        "unit_area_assumption": "גודלי הדירות 75/100/125 מ״ר הם הנחת מודל ולא הוראה של עיריית הרצליה",
        "summary": summary,
    }
