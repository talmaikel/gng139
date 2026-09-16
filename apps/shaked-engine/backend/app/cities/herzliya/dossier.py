"""התיק — מה שהלקוח באמת קונה.

‏`assess()` מחשב שרשרת מלאה: סטטוס, ציטוט עמוד ונימוק לכל שער ב-1–9.
‏**ושום נתיב לא החזיר אותה.** מסך הסינון קיבל סיכום — סטטוס, קומות
ורשימת חוסמים — ובזה נגמר. לקוח ששילם קיבל שורה בטבלה עם כתובת ותאריך.

שלוש הדרישות שמעצבות את המבנה כאן, וכולן מ-§10 ב-PRD:

  **DOS-02** · *״זיהוי חד־משמעי, גאומטריה ושטח, מספר דירות קיים ממקור
  מספק, ראיות לכללי הסף, מקור ומועד לנתונים הקריטיים, ותרחיש כלכלי
  שניתן לחשב לפי מפרט ההנחות״* — ולכן `evidence` אינו נספח אלא פרק.

  **DOS-03** · *״היעדר מסמך שאינו קריטי מצוין במפורש ואינו מוצג כארכיון
  מלא. היעדר ראיה קריטית אינו מוחלף באומדן שמאפשר לעבור תנאי סף.
  **אין להפוך נתון חסר לאפס.**״* — ולכן `gaps` הוא פרק ראשי ולא הערת
  שוליים, והתסריט הכלכלי נושא את `is_deliverable` שלו.

  **DOS-04** · *״התוצר כולל גרסת נתונים, כללים ותבנית״*.

‏**ACC-08:** *״בקשה של חברה ללא הרשאה לתיק נדחית גם כשמזהה התיק ידוע״*.
הבדיקה כאן היא על רישום מסירה, ו-404 ולא 403 — ‏403 מאשר שהמזהה קיים.
"""
import re
import statistics
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.cities.herzliya import new_build_prices, rights
from app.core.config import get_settings
from app.evidence import DECIDING, Certainty
from app.models.opportunity import Opportunity
from app.models.package import Delivery
from app.services.dwelling_units import load_units, resolve_existing_unit_area
from app.services.economic.assumptions import AssumptionStatus, get_assumptions
from app.services.economic.betterment import (
    betterment_from_land_values, breakeven_betterment,
    breakeven_land_value_per_right, levy_range, residual_land_value,
)
from app.services.market_data.repository import find_latest_valuation
from app.services.economic.calculator import calculate_feasibility
from app.services.economic.construction_costs import (
    resolve_construction_cost_per_sqm, resolve_underground_cost_per_sqm,
)
from app.services.economic.schemas import FeasibilityInput
from app.services.evidence_store import fields_for, stale_fields

TEMPLATE_VERSION = "dossier-1"

# שמות השדות בעברית, **בשרת ולא בדפדפן**. הגרסה הראשונה החזיקה אותם
# ב-`labels.ts` בלבד, וה-PDF — המסמך שהלקוח באמת מקבל ביד — הדפיס
# ‏`renewal_policy_category` ו-`scope_buildings`. כל צרכן של התיק מקבל
# עכשיו את התווית מאותו מקום.
FIELD_LABEL = {
    "parcel_area": "שטח המגרש",
    "units": "מספר דירות קיים",
    "floors": "מספר קומות קיים",
    "existing_area": "שטח בנוי קיים",
    "street_width": "רוחב הרחוב",
    "street_width_verified": "רוחב הרחוב נמדד בשיטה המאומתת",
    "street_narrow_frontages": "חזיתות צרות מ-8 מ׳",
    "street_frontages": "מספר חזיתות לרחוב",
    "pilotis": "קומת עמודים",
    "registration_area": "אזור רישום",
    "in_tama70": 'בתחום תמ"א 70',
    "scope_buildings": "מספר מבנים בחלקה",
    "renewal_policy_category": "קטגוריה במפת המדיניות",
    "category_ceiling": "תקרת הקטגוריה",
    "residential_zoning": "ייעוד למגורים",
    "zoning_names": "שמות הייעוד בתכנית",
    "residential_share": "שיעור השימוש למגורים",
    "permit_date": "מועד ההיתר",
    "strengthened": "בוצע חיזוק בהיתר",
    "occupied": "יוזמה פעילה של אחר",
    "post_2005_permit": "היתר אחרי 18.5.2005",
}

# ההנחות הכלכליות. **התווית חיה כאן ולא בדפדפן.** עד היום היא הייתה
# ב-`frontend/src/lib/labels.ts` בלבד, והמפה נשרה מהקוד: `betterment_levy_ratio`
# שונה ל-`betterment_levy_rate` ונוסף `betterment_base_ils`, והמסך המשיך
# להציג את המזהה הגולמי ליזם — בלי שגיאה, בלי בדיקה אדומה, בדיוק בשורה
# שמסבירה למה התרחיש אינו נמסר. ‏`test_labels.py` הופך את הנשירה הזו
# לבדיקה שנופלת.
ASSUMPTION_LABEL = {
    "sale_price_per_sqm_ils": "מחיר מכירה למ״ר",
    "construction_cost_per_sqm_ils": "עלות בנייה למ״ר",
    "demolition_cost_per_unit_ils": "הריסה ליחידת דיור",
    "soft_cost_ratio": "עלויות רכות",
    "developer_profit_target_ratio": "רווח יזמי מזערי",
    "main_area_ratio": "שיעור השטח העיקרי",
    "underground_ratio": "שיעור חניון תת-קרקעי",
    "underground_cost_per_sqm_ils": "עלות חניון למ״ר",
    "average_existing_unit_sqm": "שטח דירה קיימת ממוצע",
    "tenant_compensation_sqm_per_existing_unit": "תוספת שטח לדייר",
    "tenant_rent_months": "חודשי שכירות לדיירים",
    "tenant_monthly_rent_ils": "שכר דירה חודשי לדייר",
    "tenant_moving_cost_ils": "הובלות לדייר",
    "tenant_legal_cost_per_unit_ils": "עורך דין ושמאי לדייר",
    "marketing_ratio": "שיווק ותיווך",
    "guarantees_ratio": "ערבויות וביטוח",
    "finance_ratio": "מימון",
    "betterment_levy_rate": "שיעור היטל ההשבחה",
    "betterment_base_ils": "ההשבחה שעליה מוטל ההיטל",
    "vat_rate": "מס ערך מוסף",
}

_UNIT_AREA_SOURCE = {
    "verified_schedule": "לוח דירות מהיתר, אומת ידנית",
    "unverified_schedule": "לוח דירות מהיתר — נקרא ולא אומת",
    "footprint_average": "ממוצע מטביעת הרגל — אינו מתאים לאף דירה בפועל",
    "none": "לא נמצא לוח דירות ולא שטח בנוי",
}

CERTAINTY_LABEL = {
    "official": "רשמי", "derived": "נגזר", "manually_verified": "אומת ידנית",
    "community": "קהילתי", "ocr_candidate": "קריאת OCR", "ai_candidate": "קריאת מודל",
    "estimate": "אומדן", "missing": "נבדק ולא נמצא", "conflict": "סתירה בין מקורות",
}


class NotEntitled(Exception):
    """אין לחברה רישום מסירה על ההזדמנות. ‏ACC-08."""


async def _entitlement(session, opportunity_id: UUID, company_id: UUID) -> Delivery:
    row = (await session.execute(
        select(Delivery).where(Delivery.opportunity_id == opportunity_id,
                               Delivery.company_id == company_id)
    )).scalar_one_or_none()
    if row is None:
        raise NotEntitled("התיק אינו במאגר החברה")
    return row


# ‏B8 · שמות מהמקורות הגיעו ליזם כמו שהם: ״LEGAL_AREA״, ״amudim״,
# ״15.5 מ׳ residential״, ״סכום num_aprt״. במסד הם נשארים — הם המיקום
# המדויק בתוך המקור, ומי שבודק אותנו צריך אותם. בתיק מוצג שם בעברית,
# והשם המקורי בסוגריים כשהוא מה שמאתרים לפיו.
_SOURCE_TERMS = {
    # שמות שדות בשכבות — נשארים בסוגריים, כי לפיהם מאתרים את השדה במקור
    "LEGAL_AREA": "השטח הרשום בשכבת החלקות (LEGAL_AREA)",
    "amudim": "שדה קומת העמודים בשכבת הכתובות (amudim)",
    "num_aprt": "מספר הדירות (num_aprt)",
    "Num_floors": "מספר הקומות (Num_floors)",
    "WFS": "שליפה משכבת החלקות הרשמית (WFS)",
    # סוג הדרך ב-OpenStreetMap — תיאור, לא מזהה, ולכן בלי סוגריים
    "residential": "רחוב מגורים",
    "living_street": "רחוב משולב",
    "tertiary": "דרך שלישונית",
    "secondary": "דרך משנית",
    "primary": "דרך ראשית",
    "unclassified": "דרך לא מסווגת",
}
_SOURCE_TOKEN = re.compile(r"(?<![A-Za-z_])(" + "|".join(sorted(_SOURCE_TERMS, key=len, reverse=True))
                           + r")(?![A-Za-z_0-9])")


def _readable(text: str | None) -> str | None:
    """מיקום או שיטה של ראיה, בעברית. מילה שאינה במילון נשארת כמו שהיא."""
    if not text:
        return text
    return _SOURCE_TOKEN.sub(lambda m: _SOURCE_TERMS[m.group(1)], text)


def _evidence_rows(fields: dict[str, dict]) -> list[dict[str, Any]]:
    """כל שדה מהותי עם מקורו, מועדו וודאותו — ‏DOS-02.

    שורות `MISSING` נכללות **בכוונה**: ״נבדק ולא נמצא״ הוא ממצא, ותיק
    שמשמיט אותו נקרא כאילו איש לא בדק.
    """
    out = []
    for name, f in sorted(fields.items()):
        source = f.get("source") or {}
        out.append({
            "field": name,
            "label": FIELD_LABEL.get(name, name),
            "value": f.get("value"),
            "certainty": f.get("certainty"),
            "certainty_label": CERTAINTY_LABEL.get(f.get("certainty"), f.get("certainty")),
            "decides": f.get("certainty") in DECIDING,
            "source_url": source.get("url"),
            "retrieved_at": source.get("retrieved_at"),
            "location": _readable(f.get("location")),
            "method": _readable(f.get("method")),
        })
    return out


def _named(ids) -> list[dict[str, str]]:
    return [{"id": i, "label": FIELD_LABEL.get(i, i)} for i in ids]


def _gaps(assessment: dict, fields: dict[str, dict], economics: dict) -> dict[str, Any]:
    """מה שאינו ידוע, במפורש — ולא כאפס ולא כשתיקה."""
    unknown = [{"id": c["id"], "label": c["label"], "detail": c.get("detail")}
               for c in assessment["checks"] if c["status"] == "unknown"]
    missing = [n for n, f in fields.items() if f.get("certainty") == Certainty.MISSING.value]
    # ״מעולם לא נשאל״ ו״אין לו מקור פתוח״ הופיעו שניהם על אותו שדה, וזה
    # קורא כמו רשלנות: שער שאין לו מקור לא ״לא נשאל״ — הוא נשאל ואין
    # ממי לקבל תשובה. כל שדה מופיע בקטגוריה אחת בלבד.
    never_asked = sorted(set(rights.THRESHOLD_IDS) - set(fields) - set(rights.UNOBTAINABLE))
    return {
        "unknown_gates": unknown,
        # שער שאין לו מקור פתוח — גבול הנתונים, לא עבודה חסרה.
        # ‏`{id, label}` ולא אחד מהם: התווית היא מה שמודפס, והמזהה הוא מה
        # שאפשר לסנן ולבדוק לפיו. רשימה של תוויות בלבד אינה ניתנת לבדיקה.
        "unobtainable": _named(sorted(set(rights.UNOBTAINABLE)
                                      & {c["id"] for c in assessment["checks"]
                                         if c["status"] == "unknown"})),
        "checked_and_not_found": _named(sorted(missing)),
        "never_asked": _named(never_asked),
        "stale_sources": _named(assessment.get("stale_fields", [])),
        # גם כאן `{id, label}`: היום אף מסך אינו מרנדר את השדה הזה, ומחר
        # מישהו כן — ואז מזהה גולמי חוזר למסך דרך הדלת האחורית.
        "economic_inputs_missing": [
            {"id": k, "label": ASSUMPTION_LABEL.get(k, k)}
            for k in economics.get("inputs_missing", [])],
        # ‏DOS-03: התיק אינו מציג את עצמו כארכיון מלא.
        "note": ("התיק מבוסס על מקורות ציבוריים ועל תיק הבניין העירוני. "
                 "היעדר מסמך מצוין במפורש ואינו מוצג כארכיון מלא, "
                 "ונתון חסר אינו מוחלף באומדן ואינו נספר כאפס."),
    }


def _scenario_caveats(assessment: dict, fields: dict, live: dict,
                      existing_units: int | None = None) -> list[dict[str, str]]:
    """על מה הרווח נשען ואינו ודאי — **משפטים מוכנים, נכתבים פעם אחת בשרת.** (B8)

    במעבר של B8 על 6537/120: פרק הזכויות כותב שהתקרה ״מנופחת״, והתרחיש
    מתחתיו מציג רווח של 43 מיליון ₪ בלי מילה על כך — במסך, ב-PDF ובאקסל.
    הסייג היה בתיק, רק לא ליד המספר שהוא מסייג. אותו דבר למחיר המכירה
    ולשטח הדירה: שניהם אומדן, והתרחיש לא אמר את זה באף משטח.

    סדר הרשימה הוא סדר ההשפעה: התקרה מכפילה כל שגיאה פי ארבע, ולכן ראשונה.
    מי שמרנדר מדפיס ‏`text` כמו שהוא, כמו ‏`not_delivered_reason`.
    """
    out: list[dict[str, str]] = []
    if assessment.get("cap_400_sqm") and not assessment.get("cap_400_reliable"):
        post_2005 = (fields.get("post_2005_permit") or {}).get("value")
        if post_2005 is True:
            text = ("הרווח מחושב על תקרת 400% שייתכן שהיא מנופחת: בתיק הבניין יש היתר "
                    "מאחרי 18.5.2005, ולא ידוע כמה שטח הוסיף. תוספת כזו מוחרגת מהבסיס "
                    "(§70ב(א)(1)(ב)), ואם יש כזו — התקרה והרווח נמוכים מהמוצג.")
        else:
            text = ("הרווח מחושב על תקרת 400% שייתכן שהיא מנופחת: לא נבדק בתיק הבניין "
                    "אם הותרה תוספת בנייה אחרי 18.5.2005. תוספת כזו מוחרגת מהבסיס "
                    "(§70ב(א)(1)(ב)), ואם יש כזו — התקרה והרווח נמוכים מהמוצג.")
        out.append({"id": "cap_400_unreliable", "text": text})

    area = fields.get("existing_area") or {}
    if assessment.get("cap_400_sqm") and assessment.get("cap_400_certainty") not in DECIDING:
        how = f" ({area['method']})" if area.get("method") else ""
        out.append({"id": "existing_area_estimate",
                    "text": f"השטח הבנוי הקיים, שעליו נשענת התקרה, הוא אומדן{how} ולא מדידה."})

    # ‏**W1 · 16.09 · כמה מהתקרה נכנס לפי המדיניות.** מחליף את סייג R1, שהיה חשבון
    # בלבד (תקרה ÷ קומות ÷ מגרש) והשווה שטח קומה ל-100% מהמגרש — אבל קומה בתוך
    # קווי הבניין היא כמחצית מהמגרש. ‏400% הוא תקרה בחוק ולא זכות (§70ב, מדיניות §2ה).
    cap = assessment.get("cap_400_sqm")
    policy = assessment.get("policy_area") or {}
    low, high = policy.get("low"), policy.get("high")
    if cap and low and high and (low.get("share_of_cap") or 1) < 0.995:
        span = (f"{low['sqm']:,.0f}" if abs(high["sqm"] - low["sqm"]) < 50
                else f"{low['sqm']:,.0f}–{high['sqm']:,.0f}")
        share = (f"{low['share_of_cap']:.0%}" if abs(high["share_of_cap"] - low["share_of_cap"]) < 0.005
                 else f"{low['share_of_cap']:.0%}–{high['share_of_cap']:.0%}")
        out.append({"id": "policy_area_below_cap", "text": (
            f"לפי מדיניות הרצליה נכנסים בתוך קווי הבניין והנסיגות רק כ-{span} מ״ר, {share} "
            f"מתקרת ה-400% ({cap:,.0f} מ״ר). ‏400% הוא תקרה בחוק ולא זכות, והרווח כאן "
            "מחושב על כל התקרה — ולכן הוא גבוה ממה שייבנה לפי המדיניות.")})
    elif cap and policy.get("why"):
        out.append({"id": "policy_area_unknown", "text": (
            f"לא חושב כמה מתקרת ה-400% נכנס לפי מדיניות הרצליה: {policy['why']}. "
            "הרווח מחושב על כל התקרה, שהיא תקרה בחוק ולא זכות.")})

    # ‏**הסייג אומר שהנתון אינו מוכרע, ולא רק מאיפה הוא בא.** הנוסח הקודם
    # צירף את תווית המקור, ובחלקה עם דירה אחת מאומתת מתוך 28 יצא
    # ״שטח דירה קיימת ממוצע: לוח דירות מהיתר, אומת ידנית.״ — משפט שנקרא
    # כאישור, ברשימה שכותרתה ״על מה הרווח נשען ואינו ודאי״.
    for key, name in (("sale_price", "sale_price_per_sqm_ils"),
                      ("unit_area", "average_existing_unit_sqm")):
        item = live.get(key) or {}
        if item.get("resolved"):
            continue
        text = f"{ASSUMPTION_LABEL[name]} אינו מוכרע לחלקה: {item.get('label')}"
        covered = item.get("unit_count")
        if key == "unit_area" and covered and existing_units and covered < existing_units:
            text += f" — הלוח מכסה {covered} מתוך {existing_units} הדירות"
        out.append({"id": f"{name}_unresolved", "text": text + "."})
    return out


def _not_delivered(missing: list[str]) -> str | None:
    """המשפט שהיזם קורא כשהתרחיש אינו נמסר — **נכתב פעם אחת, בשרת.**

    היה כתוב שלוש פעמים: ב-PDF, ב-Excel ובמסך. שלושתם צירפו את
    ‏`inputs_missing` כמזהים גולמיים, ושלושתם היו צריכים להשתנות בנפרד
    כדי לתקן. מי שמרנדר מדפיס עכשיו מחרוזת מוכנה ואינו מחבר נוסח משלו.
    """
    if not missing:
        return None
    names = ", ".join(ASSUMPTION_LABEL.get(k, k) for k in missing)
    return ("התרחיש אינו נמסר כתוצאה, משום שאינו נשען על הנחה שלמה. "
            f"מה שאינו ידוע: {names}.")


# ‏15.09.2026 · הבסיס לאומדן מחיר דירה חדשה בהרצליה (ראו assumptions.py).
_CITY_PRICE_BASIS = "עסקאות יד שנייה ליד החלקות (GovMap) × פער חדש/יד שנייה בהרצליה (מדלן, 15.09)"


async def _resolve_live_inputs(session, opp: Opportunity, fields: dict, a) -> dict[str, Any]:
    """שני קלטים שיש להם מקור אמיתי לכל חלקה — ולא הנחה אחידה לעיר.

    **זה התפר שנוצר משתי עבודות מקבילות.** ‏B1 בנה הערכת שווי לכל חלקה
    מעסקאות שכנות, ו-B3 בנה חילוץ שטח דירה מהגרמושקה — ושניהם נכתבו אל
    המסלול של ה-worker. התיק שהמסך מציג ללקוח המשיך לקרוא
    ‏`45,000 ₪/מ״ר` ו-`70 מ״ר` מספריית ההנחות, כלומר **העבודה של שניהם
    לא הייתה נראית ליזם.**

    הפונקציה קוראת בלבד ואינה פונה לרשת: נקודת קצה שמושכת עסקאות בזמן
    בקשה הופכת פתיחת תיק לתלויה בשרת חיצוני.
    """
    out: dict[str, Any] = {}

    # ── מחיר מכירה · B1 ──
    valuation = await find_latest_valuation(
        session, opportunity_id=opp.id,
        max_age_days=get_settings().source_max_age_days)
    # ‏**`is_unit_mix_adjusted` — הגייט הזה הוא של חן, מ-PR #12.**
    # ‏B1 מחשב מחיר משוקלל *מתוך* תמהיל דירות. משקל שנגזר מתמהיל מומצא
    # מייבא הנחה בשקט ומציג אותה כנתון מעסקאות. הגרסה הראשונה שלי
    # השתמשה בכל הערכה שנמצאה, וכך החלישה כלל שהוא בנה ב-B1. כשהתמהיל
    # אינו מפורש ומלא — נשארים על הנחת העיר, וההערכה עדיין נחשפת בתיק.
    #
    # ‏**15.09 · וגם תמהיל מלא אינו מספיק: המחיר צריך להיות של דירה חדשה.**
    # ‏B15 שומר תמהיל, ו-B1 משקלל לפיו את עסקאות GovMap — שהן דירות יד
    # שנייה. בסימולציה המחיר ירד מ-42,000 ל-31,768, סומן ״נתון״, והרווח
    # באלוף יגאל אלון 40 עבר מ-11% להפסד. מחיר יד שנייה הוא הצד ״לפני״
    # של ההשבחה (`existing_price`), ולא ההכנסות. רק הערכה של דירות חדשות
    # (B12) מכריעה כאן.
    if (valuation and valuation.blended_price_per_sqm_ils
            and valuation.is_unit_mix_adjusted
            and valuation.price_basis == "new_build"):
        out["sale_price"] = {
            "value": valuation.blended_price_per_sqm_ils,
            "resolved": True,
            "certainty": Certainty.DERIVED.value,
            "label": f"‏{valuation.comparable_count} עסקאות ברדיוס "
                     f"{valuation.radius_m} מ׳, נכון ל-{valuation.as_of_date}",
            "source_url": valuation.source_url,
            "as_of_date": str(valuation.as_of_date),
            "comparable_count": valuation.comparable_count,
            "warnings": list(valuation.warnings),
        }
    else:
        # ‏**P1 · 15.09 · מחיר לפי גוש לפני האומדן האחיד לעיר.** טבלת מחירי
        # דירות חדשות לפי גוש (בועז). גוש שאינו בטבלה נשאר על 42,000. שניהם
        # אומדן — לא עסקאות של החלקה — ולכן `resolved=False` בשניהם.
        price, block_label = new_build_prices.sale_price(opp.block, a.sale_price_per_sqm_ils.value)
        city_label = f"אומדן אחיד לעיר, {a.sale_price_per_sqm_ils.value:,.0f} ₪ — {_CITY_PRICE_BASIS}"
        out["sale_price"] = {
            "value": price, "resolved": False,
            "certainty": Certainty.ESTIMATE.value,
            "basis": "block_table" if block_label else "city_estimate",
            # המספר נקרא מהספרייה ולא נכתב כאן, כדי שהתווית לא תשקר כשהערך ישתנה.
            "label": ((block_label or city_label) + ". "
                      + ("לא נמצאה הערכת שווי עדכנית לחלקה" if not valuation
                         else "העסקאות ליד החלקה הן של דירות יד שנייה, ולכן אינן קובעות "
                              "מחיר לבניין חדש" if valuation.price_basis != "new_build"
                         else "יש הערכת שווי לחלקה, אך תמהיל הדירות אינו מפורש ומלא, "
                              "ולכן המחיר המשוקלל אינו מכריע")),
            # ההערכה נחשפת גם כשאינה מכריעה: היזם רואה את העסקאות.
            "valuation_present": valuation is not None,
            "comparable_count": valuation.comparable_count if valuation else None,
        }

    # ── שטח דירה קיימת · B3 ──
    resolution = resolve_existing_unit_area(
        await load_units(session, opp.id),
        municipal_unit_count=opp.existing_units,
        existing_area_sqm=_numeric(fields.get("existing_area")),
    )
    # ‏**מחיר דירה חדשה ומחיר דירה קיימת אינם אותו מספר, ובלבלתי ביניהם.**
    # ההכנסות מחושבות לפי מחיר דירה **חדשה**. שווי המצב הקיים — הצד
    # ה״לפני״ של ההשבחה — הוא מחיר דירה **קיימת** באזור, והוא נמוך
    # משמעותית.
    #
    # ‏**15.09 · החציון של עסקאות ההשוואה, ולא המחיר המשוקלל.** הגרסה
    # הקודמת לקחה את `blended_price_per_sqm_ils`, שקיים רק כשיש תמהיל
    # **לבניין החדש** (B15) — כלומר משקלל עסקאות קיימות לפי תמהיל של
    # פרויקט שעוד לא נבנה, ובפועל לא היה קיים באף תיק. הצד ה״לפני״ הוא
    # הבניין הקיים, ולכן החציון של עסקאות היד השנייה סביבו (B16: ‏28–40
    # עסקאות לחלקה, כמעט כולן יד שנייה) הוא המספר הנכון, והוא אינו תלוי
    # בתמהיל. זה החיבור שחסר כדי שאומדן ההיטל ״בשיטת היזם״ יוצג.
    out["existing_price"] = _existing_price(valuation)

    out["unit_area"] = {
        # ‏`may_decide` הוא של B3 ולא שלנו: ודאות מכריעה, לוח שלם, ובלי
        # סתירה מול הספירה העירונית. אנחנו רק מכבדים אותו.
        "value": resolution.average_existing_unit_sqm,
        "resolved": resolution.may_decide,
        "certainty": resolution.certainty.value,
        "label": _UNIT_AREA_SOURCE.get(resolution.source, resolution.source),
        "per_unit_detail_available": resolution.per_unit_detail_available,
        "unit_count": resolution.unit_count,
        "notes": list(resolution.notes),
    }
    return out


def _unit_mix(opp: Opportunity, a) -> dict[str, Any]:
    """‏B15 · התמהיל שהיזם חישב במסך ״תמהיל ורווחיות״, כפי שנשמר לחלקה.

    ‏**התמהיל מוצג ואינו משנה את הרווח** (בועז, 15.09): ההדגמה ביום רביעי
    נשענת על המספרים שבתיק, והתמהיל נכנס אליהם רק אחרי שייבדק. המשפט
    נכתב כאן ולא במסך, כדי שהמסך, ה-PDF והאקסל יאמרו אותו דבר.
    """
    meta = opp.metadata_json or {}
    rows = [r for r in (meta.get("planned_unit_mix") or [])
            if isinstance(r, dict) and r.get("units")]
    info = meta.get("planned_unit_mix_meta") or {}
    if not rows or info.get("source") != "b15_profit_optimizer":
        return {"rows": [], "summary": None}

    rows = sorted(rows, key=lambda r: r["rooms"])
    developer_units = sum(int(r["units"]) for r in rows)
    parts = " · ".join(f'{int(r["units"])} × {r["rooms"]:g} חד׳ ({r["area_sqm"]:,.0f} מ״ר)'
                       for r in rows)
    comp = info.get("compensation_sqm_per_existing_unit")
    summary = f"תמהיל דירות ליזם (אומדן): {parts} — {developer_units} דירות ליזם"
    if info.get("tenant_units"):
        summary += f' ו-{info["tenant_units"]} לבעלי הדירות'
    if comp is not None:
        summary += f" · לפי תוספת של {comp:g} מ״ר לכל דירה קיימת"
    if info.get("existing_units_basis") == "building_average":
        summary += " · שטח הדירות הקיימות לפי ממוצע הבניין"
    # ‏באלוף יגאל אלון 6 מכפיל הדירות מתיר 30 דירות ליזם, ו-1,261 מ״ר מתוך
    # 4,461 לא נכנסים לאף תמהיל. הרווח בתיק מוכר את כל השטח, ולכן זה נאמר.
    unused, available = info.get("unused_developer_sqm"), info.get("developer_available_sqm")
    if unused and available and unused > 0.05 * available:
        summary += (f" · {unused:,.0f} מ״ר מתוך {available:,.0f} ליזם לא נכנסים לתמהיל "
                    "(מגבלת מספר הדירות), והרווח בתיק מניח שהם נמכרים")
    library_comp = a.tenant_compensation_sqm_per_existing_unit.value
    if comp is not None and abs(comp - library_comp) > 1e-9:
        summary += f" · הרווח בתיק עדיין מחושב לפי {library_comp:g} מ״ר"
    return {
        "rows": rows,
        "developer_units": developer_units,
        "tenant_units": info.get("tenant_units"),
        "compensation_sqm_per_existing_unit": comp,
        "existing_units_basis": info.get("existing_units_basis"),
        "status": info.get("status", "estimate"),
        "generated_at": info.get("generated_at"),
        "summary": summary,
    }


# פחות מזה חציון אינו מייצג; עדיף סף בלבד מאשר אומדן על שלוש עסקאות.
MIN_EXISTING_COMPARABLES = 5


def _existing_price(valuation) -> dict[str, Any]:
    """מחיר מ״ר של דירה **קיימת** ליד החלקה — הצד ה״לפני״ של ההשבחה."""
    sales = {c.source_deal_id: c for c in (valuation.comparable_sales if valuation else [])}
    if len(sales) < MIN_EXISTING_COMPARABLES:
        return {"value": None, "resolved": False, "certainty": Certainty.MISSING.value,
                "label": ("אין מספיק עסקאות השוואה בדירות קיימות"
                          + (f" ({len(sales)} עסקאות)" if sales else "")
                          + " — אין אומדן להשבחה, רק סף")}
    median = statistics.median(c.price_per_sqm_ils for c in sales.values())
    return {"value": round(median), "resolved": True,
            "certainty": Certainty.DERIVED.value,
            "comparable_count": len(sales),
            "label": (f"חציון {len(sales)} עסקאות בדירות קיימות ברדיוס {valuation.radius_m} מ׳, "
                      f"{valuation.lookback_months} חודשים (GovMap), נכון ל-{valuation.as_of_date}")}


def _numeric(field: dict | None) -> float | None:
    try:
        return float((field or {}).get("value"))
    except (TypeError, ValueError):
        return None


# ארבע הקטגוריות שהסף מפצל אליהן. הן אינן ניסוח אלא שדה מדורג, כי
# המשמעות שלהן שונה לחלוטין: ״אין סף״ אינו ״גבולי מאוד״.
#
# ‏**״לא דורג״ אינו ״עמיד״.** הדירוג משווה את הסף בשווי מ״ר זכויות לסף
# ‏`MARGINAL_LAND_VALUE_ILS`, והתרגום דורש מחיר דירה קיימת ושטח בנוי קיים.
# כשאחד מהם חסר, הקוד נפל ל״עמיד״: ‏9661 הוצגה ״עמיד״ בירוק עם 9% רווח
# על העלות — רק כי לא היה עם מה להשוות.
NO_THRESHOLD, RESILIENT, MARGINAL, UNRATED = "no_threshold", "resilient", "marginal", "unrated"
BETTERMENT_CATEGORY_LABEL = {
    NO_THRESHOLD: "לא עומד ברווח היזמי המזערי גם בלי היטל — הבעיה אינה ההיטל",
    RESILIENT: "עמיד — ההשבחה צריכה להיות גבוהה במיוחד כדי להוריד את הרווח מתחת למזערי",
    MARGINAL: "גבולי — ההשבחה היא שתכריע",
    UNRATED: ("לא דורג — חסר מחיר דירה קיימת או שטח בנוי קיים, ולכן אי אפשר "
              "לתרגם את הסף לשווי מ״ר זכויות ולומר אם הוא גבוה או נמוך"),
}
# מתחת לזה הסף נמוך מכדי לספוג שווי קרקע סביר באזור מרכזי. אומדן גס
# ומכוון ככזה: הוא מדרג בין מועמדים ואינו קובע כדאיות.
MARGINAL_LAND_VALUE_ILS = 10_000.0


def _betterment(inputs, a, live: dict, cap: float, existing_area: float | None,
                result=None) -> dict[str, Any]:
    # ‏W2 · ‏`cap` הוא השטח שעליו התרחיש מחושב: שטח המדיניות, או תקרת ה-400% להשוואה.
    """‏B11 · הסף, ולא אומדן של ההשבחה.

    מפורט ב-`POC/layer_a/data/BETTERMENT_BASE.md`. בקצרה: אנחנו לא
    יודעים את ההשבחה ולא נמציא אותה. אנחנו יודעים את **כל** שאר
    הקלטים, ולכן אפשר לחשב את ההשבחה שמאפסת את הרווח ולומר אותה.

    וההיפוך הוא מה שהופך את זה לשימושי: הסף מתורגם ל**שווי מ״ר
    זכויות** — המקדם היחיד שחסר בשיטה שחברות יזמיות מריצות בפועל.
    ‏״229 מיליון״ אינו מספר שיזם שופט; ״33,705 ₪ למ״ר זכויות״ כן.
    """
    rate = a.betterment_levy_rate.value
    target = a.developer_profit_target_ratio.value

    # ‏**E1 · 15.09 (בועז): הסף הוא ההיטל שמשאיר רווח יזמי של 16%, לא רווח
    # אפס.** יזם אינו עובד ברווח אפס. הגרסה הקודמת קראה ״עמיד״ לפרויקט
    # שכבר היה מתחת ליעד לפני כל היטל, ואומדן ההיטל חושב ביעד אחר מהסף.
    def above_target(x: float) -> float:
        r = calculate_feasibility(inputs.model_copy(update={"betterment_base_ils": x}),
                                  missing_inputs=[])
        return r.projected_profit_ils - target * r.total_cost_ils

    threshold = breakeven_betterment(above_target, rate=rate)

    # התוספת היא השטח החדש פחות הקיים. בתקרה זה שלושה רבעים ממנה (400% מהקיים).
    added = (cap - existing_area if existing_area else cap - cap / 4) if cap else None
    existing_price = live["existing_price"]["value"]
    per_right = breakeven_land_value_per_right(
        threshold, existing_area_sqm=existing_area,
        existing_value_per_sqm_ils=existing_price,
        new_rights_sqm=cap)

    # ── אומדן ראשוני, בשיטה שחברות יזמיות מריצות — ובמקדם נגזר ──
    #
    # הגיליון שהתקבל מחברה יזמית מניח 12,000 ₪ למ״ר זכויות. כאן המספר
    # הזה **נגזר** במקום להיות מונח: שווי הקרקע השיורי הוא מה שנשאר
    # מההכנסות אחרי כל העלויות ואחרי הרווח היזמי הנדרש.
    # ‏**האומדן מנוע, וזו מסקנה ולא מגבלה טכנית.**
    #
    # השיטה דורשת שני מחירים **שונים**: מחיר דירה חדשה (הכנסות) ומחיר
    # דירה קיימת (הצד ה״לפני״). היום שניהם מגיעים מאותו
    # ‏`blended_price_per_sqm_ils` — עסקאות ההשוואה של GovMap, שאינן
    # מסוננות לחדש מול יד שנייה. כשאותו מספר משמש בשני הצדדים, שווי
    # המצב הקיים יוצא גבוה משווי הזכויות החדשות ו״אין השבחה״ בכל חלקה.
    #
    # להזין יחס מומצא בין ישן לחדש היה מייצר אומדן שנראה מבוסס ואינו.
    # **הסף אינו תלוי בזה** ומוצג בכל מקרה.
    estimate = None
    prices_are_distinct = (existing_price is not None
                           and live["sale_price"]["value"] != existing_price)
    if existing_area and cap and prices_are_distinct and result is not None:
        land = residual_land_value(
            total_revenue_ils=result.total_revenue_ils,
            total_cost_ils=result.total_cost_ils,
            land_cost_ils=result.land_cost_ils,
            finance_ratio=a.finance_ratio.value,
            developer_profit_target_ratio=a.developer_profit_target_ratio.value)
        if land > 0:
            estimate = betterment_from_land_values(
                existing_area_sqm=existing_area,
                existing_value_per_sqm_ils=existing_price,
                new_rights_sqm=cap,
                land_value_per_right_ils=land / cap)
            estimate.notes.append(
                f"שווי מ״ר זכויות נגזר ולא הונח: {land / cap:,.0f} ₪ — "
                "מה שנשאר מההכנסות אחרי כל העלויות ואחרי הרווח היזמי")
    band = levy_range(breakeven_betterment_ils=threshold, estimate=estimate, rate=rate)

    if threshold is None:
        category = NO_THRESHOLD
    elif per_right is None:
        category = UNRATED
    elif per_right >= MARGINAL_LAND_VALUE_ILS:
        category = RESILIENT
    else:
        category = MARGINAL

    return {
        "rate": rate,
        "levy": band,
        # ‏B13 · המשפט שמחליף את ״היטל השבחה: 0 ₪״ — **נכתב פעם אחת, בשרת.**
        # ה-PDF, האקסל והמסך מדפיסים אותו כמו שהוא, כמו `not_delivered_reason`,
        # ולכן הניסוח אינו יכול להיות שונה בין המשטחים.
        "summary": _levy_summary(category, band, estimate, target),
        "profit_target_ratio": target,
        "estimate": None if estimate is None else {
            "betterment_ils": estimate.betterment_ils,
            "before_ils": estimate.before_ils,
            "after_ils": estimate.after_ils,
            "land_value_per_right_ils": estimate.after_ils / estimate.new_rights_sqm,
            "notes": estimate.notes,
        },
        "estimate_withheld_because": (
            None if estimate is not None else
            ("אין עסקאות השוואה בדירות קיימות באזור"
             if existing_price is None else
             "מחיר דירה חדשה ומחיר דירה קיימת מגיעים מאותן עסקאות ואינם "
             "מופרדים. בלי הפרדה, אומדן ההשבחה יוצא אפס בכל חלקה — "
             "והסף אינו תלוי בכך")),
        "breakeven_ils": threshold,
        "breakeven_per_added_sqm_ils": threshold / added if threshold and added else None,
        # המספר שיזם שופט בשנייה.
        "breakeven_land_value_per_right_ils": per_right,
        "category": category,
        "category_label": BETTERMENT_CATEGORY_LABEL[category],
        # ‏15.09 · מאז שהאומדן בשיטת היזם מוצג (#64), ״מוצג סף ולא מספר״
        # נכתב מתחת למספר. הנוסח נגזר ממה שבאמת מוצג.
        "note": (f"הסף אינו שומה. הוא אומר עד איזה היטל הפרויקט עוד משאיר רווח יזמי של {target:.0%}. "
                 "שיעור ההיטל — רבע ההשבחה לפי §19(ב)(10א) — ודאי; הבסיס "
                 + ("דורש שומה. האומדן מחושב בשיטת היזם — שווי הזכויות פחות "
                    "שווי הדירות הקיימות — ואינו שומה."
                    if estimate is not None else
                    "אינו ידוע, ולכן מוצג סף ולא מספר.")),
        # **הסף יורש את כל הקלטים של המחשבון.** כשאחד מהם עדיין אינו
        # מוכרע — שטח דירה ממוצע, למשל — הסף זז איתו. שתיקה על כך
        # הייתה הופכת מספר תלוי-הנחה למספר שנראה נחרץ.
        "rests_on_unresolved_inputs": sorted(
            k for k, v in {"שטח דירה קיימת ממוצע": live["unit_area"]["resolved"],
                           "מחיר מכירה למ״ר": live["sale_price"]["resolved"]}.items()
            if not v),
    }


def _profit_verdict(result, target: float, after_levy: bool = False) -> str:
    """‏*״הרווח היזמי חייב להיות מעל 16% כדי שיהיה כדאי״* (בועז, 15.09).

    הרווח הוצג במספר גדול ובצבע, והמשפט ״מתחת ליעד״ לא נאמר במילים —
    יזם שקרא 31 מיליון ₪ לא ראה שהפרויקט אינו עומד בסף שלו.
    """
    margin = result.profit_margin_on_cost_ratio
    # ‏W2 · נקודה 7: הרווח שנשפט הוא אחרי אומדן ההיטל כשיש אומדן.
    if after_levy:
        side = "מעל הרווח היזמי המזערי" if result.meets_developer_target else "מתחת לרווח היזמי המזערי"
        return f"{side} ({target:.0%}): {margin:.1%} על העלות, אחרי אומדן היטל השבחה"
    if result.meets_developer_target:
        return f"מעל הרווח היזמי המזערי ({target:.0%}): {margin:.1%} על העלות, לפני היטל השבחה"
    return (f"מתחת לרווח היזמי המזערי ({target:.0%}): {margin:.1%} על העלות, "
            "עוד לפני היטל השבחה")


_CATEGORY_SHORT = {NO_THRESHOLD: "לא כדאי", RESILIENT: "עמיד", MARGINAL: "גבולי",
                   UNRATED: "לא דורג"}


def _millions(ils: float) -> str:
    return f"{ils / 1e6:,.1f} מיליון ₪"


def _levy_summary(category: str, band: dict, estimate, target: float) -> str:
    """שורת ההיטל בתיק: **לא ידוע**, ומה כן ידוע — עד כמה הפרויקט סופג אותו.

    ‏״0 ₪״ נקרא כמו ״אין היטל״, והוא שקר: ההיטל הוא רבע מההשבחה, והבסיס
    דורש שומה. מה שכן אפשר לומר הוא התקרה — ההיטל שמעליו הרווח מתאפס.
    """
    # ‏W2 · כשיש אומדן, הוא נכנס לרווח — ולכן ההיטל אינו ״לא ידוע״ אלא אומדן שאינו שומה.
    known = "אומדן ולא שומה" if estimate is not None and band.get("low_ils") is not None else "לא ידוע"
    if category == NO_THRESHOLD or not band.get("viable_up_to_ils"):
        # ‏E1 · מתחת ל-16% עוד לפני היטל. האומדן עדיין נאמר: הוא אומר בכמה
        # עוד יירד הרווח, וזה מה שיזם ישאל מיד אחרי ״לא כדאי״.
        text = (f"היטל השבחה: {known} · הפרויקט אינו מגיע לרווח יזמי של {target:.0%} "
                "גם בלי היטל — הבעיה אינה ההיטל")
    else:
        text = (f"היטל השבחה: {known} · רווח של {target:.0%} נשמר כל עוד ההיטל מתחת ל-"
                f"{_millions(band['viable_up_to_ils'])} ({_CATEGORY_SHORT[category]})")
    if estimate is not None and band.get("low_ils") is not None:
        # שיטת היזם: שווי המצב החדש פחות הקיים, כפול רבע. הטווח הוא ±10%
        # בשווי מ״ר הזכויות, ולכן רחב — ההיטל הוא הפרש, והוא רגיש.
        text += (f" · אומדן: כ-{band['estimate_ils'] / 1e6:,.1f} מיליון ₪ "
                 f"(טווח {band['low_ils'] / 1e6:,.1f}–{band['high_ils'] / 1e6:,.1f})")
    return text


def _assumption_rows(a, live: dict, construction_cost, construction_cost_per_sqm,
                     underground_cost, underground_cost_per_sqm) -> dict[str, dict]:
    """טבלת ״כל ההנחות״ — **השורה מציגה את הערך שהתרחיש השתמש בו.** (A20)

    לפני כן הטבלה נבנתה מספריית ההנחות של העיר, והתרחיש מעליה חושב
    מקלטים שנפתרו לחלקה: התרחיש השתמש ב-‏52,300 ₪ מעסקאות ובשטח דירה
    מהגרמושקה, והטבלה מתחתיו הציגה ״45,000 · אומדן״ ו-״70 מ״ר · חסר״.
    יזם שמשווה את שתיהן רואה מסמך שסותר את עצמו. **וגם האקסל קורא את
    הטבלה הזו** (`exports._scenario_inputs`), כך שהסתירה עברה לנוסחאות.

    ארבע שורות נפתרות לכל חלקה; כל השאר נשארות מהספרייה כמו שהן.
    צורת השורה זהה בכולן: ‏`value`, ‏`status` (‏data / estimate / missing),
    ‏`unit`, ‏`source`, ‏`label`. **‏`value` לעולם אינו ריק** — כשאין נתון
    לחלקה, זה ערך הספרייה שהתרחיש באמת השתמש בו, והסטטוס אומר את זה.
    """
    rows = {k: {**v, "label": ASSUMPTION_LABEL.get(k, k)} for k, v in a.report().items()}

    def row(key: str, value, status: str, source: str | None, **extra) -> None:
        rows[key] = {"value": value, "status": status,
                     "unit": getattr(a, key).unit, "source": source,
                     "label": ASSUMPTION_LABEL.get(key, key), **extra}

    # ‏**הסטטוס נגזר מ-`resolved` ולא מהוודאות.** לוח מאומת-ידנית שמכסה
    # דירה אחת מתוך שמונה נושא ודאות מכריעה ובכל זאת אינו מכריע לבניין;
    # ‏`resolved` הוא ההכרעה של B3 ושל הגייט של חן, ולכן הוא הקובע כאן.
    price = live["sale_price"]
    row("sale_price_per_sqm_ils", price["value"],
        "data" if price["resolved"] else a.sale_price_per_sqm_ils.status.value,
        price["label"])

    unit = live["unit_area"]
    if unit["value"] is not None:
        row("average_existing_unit_sqm", unit["value"],
            "data" if unit["resolved"] else AssumptionStatus.ESTIMATE.value,
            unit["label"])
    else:
        row("average_existing_unit_sqm", a.average_existing_unit_sqm.value,
            a.average_existing_unit_sqm.status.value, unit["label"])

    # עלות הבנייה: סקר השמאים לפי גובה הבניין, לא מציין-המקום בספרייה.
    row("construction_cost_per_sqm_ils", construction_cost_per_sqm,
        construction_cost.status, construction_cost.source,
        method=construction_cost.method,
        as_of_date=(construction_cost.as_of_date.isoformat()
                    if construction_cost.as_of_date else None))

    found = underground_cost.value_ils_per_sqm is not None
    row("underground_cost_per_sqm_ils", underground_cost_per_sqm,
        underground_cost.status if found else a.underground_cost_per_sqm_ils.status.value,
        underground_cost.source if found else a.underground_cost_per_sqm_ils.source,
        method=underground_cost.method,
        as_of_date=(underground_cost.as_of_date.isoformat()
                    if underground_cost.as_of_date else None))
    return rows


async def _economics(session, opp: Opportunity, assessment: dict, fields: dict,
                     solve_required: bool = True) -> dict[str, Any]:
    """התרחיש הגנרי — ‏PRD 6.4. **אינו דוח שמאי חתום, וזה נכתב בתיק.**"""
    cap = assessment.get("cap_400_sqm")
    a = get_assumptions(opp.city_code)
    live = await _resolve_live_inputs(session, opp, fields, a)

    # ‏**החוסמים נגזרים מהמצב בפועל ולא מהספרייה.** ‏`a.blocking()` מחזיר
    # את מה שמסומן `MISSING` בספרייה — נכון כברירת מחדל לעיר, ושגוי
    # לחלקה שיש לה לוח דירות מאושר. נתון שנפתר לחלקה הזו יורד מהרשימה;
    # נתון שלא — נשאר, וממשיך לחסום מסירה.
    # ‏**החלטה מסחרית, 14.09.2026, בועז.** שני שדות ירדו מרשימת החוסמים
    # ולא נעלמו: הם מוצגים בתיק עם תווית שאומרת בדיוק מה מצבם.
    #
    # ‏`average_existing_unit_sqm` — כשההחלטה התקבלה, הכלל ״רק מאושר
    #   מכריע״ היה בלתי-פתיר בייצור: שום קוד לא סימן
    #   `requires_human_review=False`. **מסך האישור נבנה מאז** (PR #17,
    #   טל), ולכן לוח *מאושר* כן מכריע היום. ההקלה נשארת בשביל התיקים
    #   שאיש עוד לא עבר עליהם: לוח שנקרא ולא אומת מוצג עם תווית ואינו
    #   חוסם, במקום להסתיר עבודה שנעשתה.
    #
    # ‏`betterment_base_ils` — אינו נדרש יותר: במקומו מוצג הסף, שהוא
    #   אמירה שלמה ולא חוסר. ״כדאי כל עוד ההיטל מתחת ל-X״ אינו ניחוש.
    #
    # ‏**מה שלא השתנה:** שדה שאין לו בכלל ערך עדיין חוסם. זה לא ויתור
    # על הכלל אלא צמצום שלו למה שבאמת חסר.
    #
    # B2: construction_cost_per_sqm_ils gets the same treatment -- it is
    # unconditionally MISSING in the library (see assumptions.py), and the
    # resolution below (developer figure > appraisers' survey by building
    # height > that placeholder) decides whether it actually blocks.
    SOFTENED = {"betterment_base_ils"}
    if live["unit_area"]["value"] is not None:
        SOFTENED = SOFTENED | {"average_existing_unit_sqm"}
    blocking = [k for k in a.blocking() if k not in SOFTENED and k != "construction_cost_per_sqm_ils"]
    # B2: the same resolution worker.py uses for the on-demand pipeline --
    # a.construction_cost_per_sqm_ils is a placeholder only (see
    # assumptions.py) and must never decide a scenario directly. `floors`
    # lets this pick the survey's actual height band for this building
    # instead of averaging across all three; worker.py has no rights
    # assessment to read a floor count from, so it always averages.
    #
    # `floors_low` rather than `floors_high`: `rights.floors()` scans the
    # street-width measurement's tolerance band and returns the minimum and
    # maximum permitted floor count across it. `floors_low` is the
    # conservative, guaranteed-at-least figure; `floors_high` is the
    # optimistic end of the same uncertainty. Pricing construction off the
    # optimistic count would understate cost whenever the true width lands
    # on the low side of the tolerance band.
    floors_range = assessment.get("floors") or {}
    floors = floors_range.get("low")
    construction_cost = resolve_construction_cost_per_sqm(opp.city_code, None, floors=floors)
    if construction_cost.value_ils_per_sqm is None:
        blocking.append("construction_cost_per_sqm_ils")
        construction_cost_per_sqm = a.construction_cost_per_sqm_ils.value
    else:
        construction_cost_per_sqm = construction_cost.value_ils_per_sqm

    # החניון מאותה שורה בסקר. עיר שהסקר לא מכסה נופלת להנחת הספרייה.
    underground_cost = resolve_underground_cost_per_sqm(opp.city_code)
    underground_cost_per_sqm = (underground_cost.value_ils_per_sqm
                                or a.underground_cost_per_sqm_ils.value)

    base = {
        "assumptions_version": a.version,
        "assumptions_effective_date": a.effective_date.isoformat(),
        # ‏**A20.** טבלת ההנחות מציגה את מה שהתרחיש השתמש בו, לא את
        # ברירת המחדל של העיר. ראו `_assumption_rows`.
        "assumptions": _assumption_rows(
            a, live, construction_cost, construction_cost_per_sqm,
            underground_cost, underground_cost_per_sqm),
        "live_inputs": live,
        "caveats": _scenario_caveats(assessment, fields, live, opp.existing_units),
        "unit_mix": _unit_mix(opp, a),
        "disclaimer": "בדיקת כדאיות ראשונית להשוואה. אינה דוח שמאי חתום "
                      "ואינה קובעת זכויות או היתכנות מאושרת.",
    }
    if not cap or not opp.existing_units or not opp.area_sqm:
        return {**base, "scenario": None, "inputs_missing": blocking,
                "not_delivered_reason": _not_delivered(blocking),
                "is_deliverable": False,
                "why": "אין תקרת זכויות מבוססת, ולכן לא מחושב תרחיש (DOS-03)"}

    # ‏**התרחיש קורא את הטבלה, ולא את המקורות שמאחוריה.** כך הטבלה
    # שמוצגת ליזם והקלט של החישוב הם אותו אובייקט, ואינם יכולים להיפרד
    # שוב כשמישהו יוסיף מקור חדש לאחד מהם.
    used = {k: v["value"] for k, v in base["assumptions"].items()}
    inputs = FeasibilityInput(
            plot_area_sqm=opp.area_sqm,
            existing_units=opp.existing_units,
            buildable_area_sqm=cap,
            sale_price_per_sqm=used["sale_price_per_sqm_ils"],
            construction_cost_per_sqm=used["construction_cost_per_sqm_ils"],
            soft_cost_ratio=a.soft_cost_ratio.value,
            demolition_cost_per_unit=a.demolition_cost_per_unit_ils.value,
            developer_profit_target_ratio=a.developer_profit_target_ratio.value,
            average_existing_unit_sqm=used["average_existing_unit_sqm"],
            tenant_compensation_sqm_per_existing_unit=a.tenant_compensation_sqm_per_existing_unit.value,
            main_area_ratio=a.main_area_ratio.value,
            underground_ratio=a.underground_ratio.value,
            underground_cost_per_sqm=used["underground_cost_per_sqm_ils"],
            tenant_rent_months=a.tenant_rent_months.value,
            tenant_monthly_rent_ils=a.tenant_monthly_rent_ils.value,
            tenant_moving_cost_ils=a.tenant_moving_cost_ils.value,
            tenant_legal_cost_per_unit_ils=a.tenant_legal_cost_per_unit_ils.value,
            marketing_ratio=a.marketing_ratio.value,
            guarantees_ratio=a.guarantees_ratio.value,
            finance_ratio=a.finance_ratio.value,
            betterment_levy_rate=a.betterment_levy_rate.value,
            betterment_base_ils=a.betterment_base_ils.value,
            vat_rate=a.vat_rate.value,
    )
    existing_area = _numeric(fields.get("existing_area"))
    target = a.developer_profit_target_ratio.value

    def run(area: float) -> dict[str, Any]:
        return _run(inputs.model_copy(update={"buildable_area_sqm": area}), a, live,
                    existing_area, blocking)

    # ‏**W2 · 16.09 · הדוח הכלכלי נקבע לפי המדיניות, ו-400% להשוואה בלבד.**
    # ‏400% הוא תקרה בחוק ולא זכות (§70ב); הרווח עליו הוא ״מה היה אילו״.
    policy = (assessment.get("policy_area") or {}).get("base") or {}
    policy_sqm = policy.get("sqm")
    cap_run = run(cap)
    policy_run = run(policy_sqm) if policy_sqm else None
    head = policy_run or cap_run
    result, betterment, after = head["result"], head["betterment"], head["after"]

    # שורת בסיס ההשבחה בטבלה היא מה שהתרחיש השתמש בו: האומדן כשיש, ״חסר״ כשאין.
    # האקסל קורא אותה לתא הכחול, ולכן גם שם הרווח הוא אחרי אומדן ההיטל.
    if after is not None:
        base["assumptions"]["betterment_base_ils"] = {
            **base["assumptions"]["betterment_base_ils"],
            "value": after["betterment_ils"], "status": AssumptionStatus.ESTIMATE.value,
            "source": ("אומדן בשיטת היזם: שווי הזכויות (שווי קרקע שיורי) פחות שווי הדירות "
                       f"הקיימות — {betterment['levy'].get('estimate_ils', 0) / 1e6:,.1f} מיליון ₪ היטל. "
                       "אינו שומה")}

    rights_verdict = _rights_verdict(policy_run, cap_run, run, assessment, target,
                                     solve_required=solve_required)
    return {**base,
            "scenario": result.model_dump(),
            "live_inputs": live,
            "betterment": betterment,
            "after_levy": after,
            "before_levy": {"profit_ils": head["before"].projected_profit_ils,
                            "margin": head["before"].profit_margin_on_cost_ratio,
                            "meets_target": head["before"].meets_developer_target},
            "area_basis": "policy" if policy_run else "cap_400",
            "buildable_area_sqm": head["area_sqm"],
            "scenarios": {"policy": _scenario_card(policy_run, assessment) if policy_run else None,
                          "cap_400": _scenario_card(cap_run, assessment)},
            "rights_verdict": rights_verdict,
            "inputs_missing": result.inputs_missing,
            "not_delivered_reason": _not_delivered(result.inputs_missing),
            "is_deliverable": result.is_deliverable,
            # ‏E1 · המשפט ליד הרווח, בשרת — אותו נוסח במסך, ב-PDF ובאקסל.
            "profit_verdict": _profit_verdict(result, target, after_levy=after is not None),
            "buildable_basis": (_policy_basis(assessment) if policy_run
                                else assessment.get("cap_400_basis")),
            "buildable_certainty": ("estimate" if policy_run
                                    else assessment.get("cap_400_certainty"))}


def _run(inputs, a, live: dict, existing_area: float | None, blocking: list[str]) -> dict[str, Any]:
    """תרחיש אחד על שטח אחד: לפני היטל, התקרה והאומדן, ואחרי אומדן ההיטל."""
    area = inputs.buildable_area_sqm
    before = calculate_feasibility(inputs, missing_inputs=blocking)
    betterment = _betterment(inputs, a, live, area, existing_area, before)
    est = betterment.get("estimate")
    after = None
    result = before
    if est is not None:
        # ‏**W2 · נקודה 7: ״רווח על העלות — רווח יזמי אחרי היטל השבחה״.** האומדן
        # נכנס לעלות כמו שהיטל נכנס בפועל, כולל המימון עליו — אותה הנחה שעליה
        # נשענת התקרה, ולכן רווח ≥16% ⇔ ההיטל מתחת לתקרה.
        def with_levy(b: float):
            return calculate_feasibility(
                inputs.model_copy(update={"betterment_base_ils": max(b, 0.0)}), missing_inputs=blocking)
        swing = 0.10
        mid = with_levy(est["betterment_ils"])
        worst = with_levy(est["after_ils"] * (1 + swing) - est["before_ils"])
        best = with_levy(est["after_ils"] * (1 - swing) - est["before_ils"])
        after = {"betterment_ils": max(est["betterment_ils"], 0.0),
                 "levy_ils": mid.betterment_levy_ils,
                 "levy_low_ils": best.betterment_levy_ils, "levy_high_ils": worst.betterment_levy_ils,
                 "profit_ils": mid.projected_profit_ils,
                 "margin": mid.profit_margin_on_cost_ratio,
                 "margin_low": worst.profit_margin_on_cost_ratio,
                 "margin_high": best.profit_margin_on_cost_ratio,
                 "meets_target": mid.meets_developer_target}
        result = mid
    return {"area_sqm": area, "before": before, "after": after, "result": result,
            "betterment": betterment}


def _scenario_card(r: dict[str, Any], assessment: dict) -> dict[str, Any]:
    """תקציר של תרחיש אחד להשוואה בין שטח המדיניות לתקרת ה-400%."""
    b, after = r["before"], r["after"]
    plot = ((assessment.get("policy_area") or {}).get("plot_sqm"))
    return {
        "area_sqm": r["area_sqm"],
        "far_pct": r["area_sqm"] / plot * 100 if plot else None,
        "developer_allocation_sqm": b.developer_allocation_sqm,
        "total_revenue_ils": b.total_revenue_ils,
        "total_cost_before_levy_ils": b.total_cost_ils,
        "profit_before_levy_ils": b.projected_profit_ils,
        "margin_before_levy": b.profit_margin_on_cost_ratio,
        "levy_ceiling_ils": r["betterment"]["levy"].get("viable_up_to_ils"),
        "levy_estimate_ils": after["levy_ils"] if after else None,
        "profit_after_levy_ils": after["profit_ils"] if after else None,
        "margin_after_levy": after["margin"] if after else None,
        "meets_target": r["result"].meets_developer_target,
    }


def _policy_basis(assessment: dict) -> str:
    p = assessment.get("policy_area") or {}
    low, base, high = p.get("low") or {}, p.get("base") or {}, p.get("high") or {}
    return (f"שטח לפי מדיניות הרצליה, אומדן בסיס {base.get('sqm', 0):,.0f} מ״ר "
            f"(טווח {low.get('sqm', 0):,.0f}–{high.get('sqm', 0):,.0f}) — בתוך קווי הבניין והנסיגות; "
            f"תקרת 400% ({p.get('cap_400_sqm') or 0:,.0f} מ״ר) להשוואה בלבד")


REQUIRED_AREA_ITERATIONS = 30


def _rights_verdict(policy_run, cap_run, run, assessment: dict, target: float,
                    solve_required: bool = True) -> dict[str, Any]:
    """‏**W2 · האם כלכלי לפי המדיניות, ואם לא — כמה זכויות צריך לבקש.**

    ארבעה מצבים, ולא כן/לא: ״לא כלכלי לפי המדיניות וכלכלי ב-400%״ הוא בדיוק
    הטיעון של יזם מול הוועדה המקומית, ו״לא כלכלי גם ב-400%״ אומר שהגדלת
    זכויות אינה הפתרון. הרווח נשפט אחרי אומדן ההיטל כשיש אומדן, ולפניו כשאין.
    """
    p = assessment.get("policy_area") or {}
    if policy_run is None:
        return {"case": "D", "basis": None,
                "text": ("לא חושב שטח לפי מדיניות הרצליה"
                         + (f": {p['why']}" if p.get("why") else "")
                         + ". הרווח מחושב על תקרת ה-400%, שהיא תקרה בחוק ולא זכות.")}
    after = policy_run["after"] is not None
    when = "אחרי אומדן היטל השבחה" if after else "לפני היטל השבחה"
    plot = p.get("plot_sqm")
    cap = cap_run["area_sqm"]
    pm = policy_run["result"].profit_margin_on_cost_ratio
    cm = cap_run["result"].profit_margin_on_cost_ratio
    area = policy_run["area_sqm"]
    far = f" ({area / plot * 100:,.0f}% בנייה)" if plot else ""
    if policy_run["result"].meets_developer_target:
        return {"case": "A", "basis": "after_levy" if after else "before_levy",
                "text": (f"כלכלי לפי מדיניות הרצליה: {pm:.1%} על העלות {when}, "
                         f"על {area:,.0f} מ״ר{far} — מעל הרווח היזמי המזערי ({target:.0%}).")}
    if not cap_run["result"].meets_developer_target:
        return {"case": "C", "basis": "after_levy" if after else "before_levy",
                "text": (f"לא כלכלי לפי המדיניות ({pm:.1%} על העלות {when}), וגם לא בניצול מלא של "
                         f"תקרת ה-400% ({cm:.1%}). הגדלת זכויות אינה פותרת — הפער במחיר, "
                         "בעלויות או בתמורה לדיירים.")}
    if not solve_required:
        return {"case": "B", "basis": "after_levy" if after else "before_levy"}
    lo, hi = area, cap
    for _ in range(REQUIRED_AREA_ITERATIONS):
        mid = (lo + hi) / 2
        if run(mid)["result"].meets_developer_target:
            hi = mid
        else:
            lo = mid
    required = hi
    addition = required - area
    out = {"case": "B", "basis": "after_levy" if after else "before_levy",
           "required_area_sqm": required, "required_addition_sqm": addition,
           "required_share_of_cap": required / cap if cap else None,
           "required_far_pct": required / plot * 100 if plot else None,
           "addition_far_pct": addition / plot * 100 if plot else None}
    add_far = f", כ-{out['addition_far_pct']:,.0f} נקודות אחוזי בנייה" if plot else ""
    out["text"] = (f"לא כלכלי לפי המדיניות ({pm:.1%} על העלות {when}), וכלכלי בתקרת ה-400% ({cm:.1%}). "
                   f"כדי להגיע לרווח יזמי של {target:.0%} נדרשים כ-{required:,.0f} מ״ר — תוספת של "
                   f"כ-{addition:,.0f} מ״ר מעל המדיניות{add_far} ({required / cap:.0%} מהתקרה). "
                   "זה הבסיס לבקשת הגדלת זכויות מהוועדה המקומית, עד תקרת החוק.")
    return out


async def screening(session, city_rules, opportunity_id: UUID) -> dict[str, Any]:
    """‏W6 · הכלכלה של מועמד לסריקה — מקרה ושיעור רווח, בלי שום פרט מזהה.

    אותו חישוב כמו התיק (`_economics`), כך שהסריקה מדרגת לפי המספר שהלקוח
    יראה אחר כך. בלי פתרון תוספת הזכויות: הסריקה צריכה רק לדעת שהוא B.
    """
    opp = await session.get(Opportunity, opportunity_id)
    assessment = await city_rules.assess(session, opportunity_id)
    fields = await fields_for(session, opportunity_id)
    econ = await _economics(session, opp, assessment, fields, solve_required=False)
    s = econ.get("scenario") or {}
    cap = (econ.get("scenarios") or {}).get("cap_400") or {}
    cap_margin = (cap.get("margin_after_levy") if cap.get("margin_after_levy") is not None
                  else cap.get("margin_before_levy"))
    return {"case": (econ.get("rights_verdict") or {}).get("case"),
            "margin": s.get("profit_margin_on_cost_ratio"),
            "cap_margin": cap_margin,
            "after_levy": econ.get("after_levy") is not None}


async def build(session, city_rules, opportunity_id: UUID, company_id: UUID) -> dict[str, Any]:
    """התיק המלא לחלקה אחת, למי שקיבל אותה."""
    delivery = await _entitlement(session, opportunity_id, company_id)
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise NotEntitled("ההזדמנות אינה קיימת")
    return await assemble(session, city_rules, opp, delivery)


async def assemble(session, city_rules, opp: Opportunity, delivery: Delivery | None) -> dict[str, Any]:
    """התיק עצמו, **בלי בדיקת הרשאה**. ‏`build` הוא הדרך היחידה ללקוח.

    נפרד מ-`build` בשביל ‏`scripts/check_surfaces.py` (B14): ה-CI זורע
    חלקות ואינו מוסר אותן לאף חברה, ובכל זאת צריך לבנות להן תיק ולהשוות
    את המסך ל-PDF ולאקסל. בלי מסירה, שדות המסירה ריקים ולא ממוצאים.
    """
    opportunity_id = opp.id
    assessment = await city_rules.assess(session, opportunity_id)
    fields = await fields_for(session, opportunity_id)
    economics = await _economics(session, opp, assessment, fields)

    return {
        "identity": {
            "opportunity_id": str(opp.id),
            "address": opp.address,
            "block": opp.block,
            "parcel": opp.parcel,
            "city_code": opp.city_code,
            "area_sqm": opp.area_sqm,
            "existing_units": opp.existing_units,
        },
        "rights": assessment,
        "evidence": _evidence_rows(fields),
        "economics": economics,
        "gaps": _gaps(assessment, fields, economics),
        # ‏DOS-04: גרסת נתונים, כללים ותבנית.
        "versions": {
            "rules_version": (delivery and delivery.rules_version) or rights.RULES_VERSION,
            "data_version": delivery.data_version if delivery else None,
            "template_version": TEMPLATE_VERSION,
        },
        "delivery": {
            "delivered_at": (delivery.delivered_at.isoformat()
                             if delivery and delivery.delivered_at else None),
            "why_selected": delivery.why_selected if delivery else None,
        },
        "stale_fields": stale_fields(fields),
    }
