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
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.cities.herzliya import rights
from app.core.config import get_settings
from app.evidence import DECIDING, Certainty
from app.models.opportunity import Opportunity
from app.models.package import Delivery
from app.services.dwelling_units import load_units, resolve_existing_unit_area
from app.services.economic.assumptions import get_assumptions
from app.services.market_data.repository import find_latest_valuation
from app.services.economic.calculator import calculate_feasibility
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
    "pilotis": "קומת עמודים",
    "registration_area": "אזור רישום",
    "in_tama70": 'בתחום תמ"א 70',
    "scope_buildings": "מספר מבנים בחלקה",
    "renewal_policy_category": "קטגוריה במפת המדיניות",
    "category_ceiling": "תקרת הקטגוריה",
    "residential_zoning": "ייעוד למגורים",
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
    "developer_profit_target_ratio": "יעד רווח ליזם",
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
            "location": f.get("location"),
            "method": f.get("method"),
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
    if valuation and valuation.blended_price_per_sqm_ils:
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
        out["sale_price"] = {
            "value": a.sale_price_per_sqm_ils.value, "resolved": False,
            "certainty": Certainty.ESTIMATE.value,
            "label": "אומדן אחיד לעיר — לא נמצאה הערכת שווי עדכנית לחלקה",
        }

    # ── שטח דירה קיימת · B3 ──
    resolution = resolve_existing_unit_area(
        await load_units(session, opp.id),
        municipal_unit_count=opp.existing_units,
        existing_area_sqm=_numeric(fields.get("existing_area")),
    )
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


def _numeric(field: dict | None) -> float | None:
    try:
        return float((field or {}).get("value"))
    except (TypeError, ValueError):
        return None


async def _economics(session, opp: Opportunity, assessment: dict, fields: dict) -> dict[str, Any]:
    """התרחיש הגנרי — ‏PRD 6.4. **אינו דוח שמאי חתום, וזה נכתב בתיק.**"""
    cap = assessment.get("cap_400_sqm")
    a = get_assumptions(opp.city_code)
    live = await _resolve_live_inputs(session, opp, fields, a)

    # ‏**החוסמים נגזרים מהמצב בפועל ולא מהספרייה.** ‏`a.blocking()` מחזיר
    # את מה שמסומן `MISSING` בספרייה — נכון כברירת מחדל לעיר, ושגוי
    # לחלקה שיש לה לוח דירות מאושר. נתון שנפתר לחלקה הזו יורד מהרשימה;
    # נתון שלא — נשאר, וממשיך לחסום מסירה.
    blocking = [k for k in a.blocking()
                if not (k == "average_existing_unit_sqm" and live["unit_area"]["resolved"])]
    base = {
        "assumptions_version": a.version,
        "assumptions_effective_date": a.effective_date.isoformat(),
        "assumptions": {k: {**v, "label": ASSUMPTION_LABEL.get(k, k)}
                        for k, v in a.report().items()},
        "live_inputs": live,
        "disclaimer": "בדיקת כדאיות ראשונית להשוואה. אינה דוח שמאי חתום "
                      "ואינה קובעת זכויות או היתכנות מאושרת.",
    }
    if not cap or not opp.existing_units or not opp.area_sqm:
        return {**base, "scenario": None, "inputs_missing": blocking,
                "not_delivered_reason": _not_delivered(blocking),
                "is_deliverable": False,
                "why": "אין תקרת זכויות מבוססת, ולכן לא מחושב תרחיש (DOS-03)"}

    result = calculate_feasibility(
        FeasibilityInput(
            plot_area_sqm=opp.area_sqm,
            existing_units=opp.existing_units,
            buildable_area_sqm=cap,
            sale_price_per_sqm=live["sale_price"]["value"],
            construction_cost_per_sqm=a.construction_cost_per_sqm_ils.value,
            soft_cost_ratio=a.soft_cost_ratio.value,
            demolition_cost_per_unit=a.demolition_cost_per_unit_ils.value,
            developer_profit_target_ratio=a.developer_profit_target_ratio.value,
            average_existing_unit_sqm=(live["unit_area"]["value"]
                                       or a.average_existing_unit_sqm.value),
            tenant_compensation_sqm_per_existing_unit=a.tenant_compensation_sqm_per_existing_unit.value,
            main_area_ratio=a.main_area_ratio.value,
            underground_ratio=a.underground_ratio.value,
            underground_cost_per_sqm=a.underground_cost_per_sqm_ils.value,
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
        ),
        missing_inputs=blocking,
    )
    return {**base, "scenario": result.model_dump(),
            "live_inputs": live,
            "inputs_missing": result.inputs_missing,
            "not_delivered_reason": _not_delivered(result.inputs_missing),
            "is_deliverable": result.is_deliverable,
            # תקרת ה-400% נשענת על אומדן שטח קיים, וזה נכתב ולא נבלע.
            "buildable_basis": assessment.get("cap_400_basis"),
            "buildable_certainty": assessment.get("cap_400_certainty")}


async def build(session, city_rules, opportunity_id: UUID, company_id: UUID) -> dict[str, Any]:
    """התיק המלא לחלקה אחת, למי שקיבל אותה."""
    delivery = await _entitlement(session, opportunity_id, company_id)
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise NotEntitled("ההזדמנות אינה קיימת")

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
            "rules_version": delivery.rules_version or rights.RULES_VERSION,
            "data_version": delivery.data_version,
            "template_version": TEMPLATE_VERSION,
        },
        "delivery": {
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
            "why_selected": delivery.why_selected,
        },
        "stale_fields": stale_fields(fields),
    }
