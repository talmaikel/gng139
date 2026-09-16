"""שמירת תוצאת ההערכה על ההזדמנות, כדי שהיא תהיה ניתנת לסינון ולתצוגה.

`HerzliyaCityRules.assess()` מחשב את שרשרת הזכויות מהראיות. החישוב זול,
אבל הוא לכל הזדמנות בנפרד — וסינון של 699 מועמדים לפי ״מי כשיר״ אינו יכול
להריץ אותו בכל בקשה. התוצאה נשמרת ב-`metadata_json.assessment`.

**מה שבמכוון לא נעשה כאן: לא נוגעים ב-`verification_level`.**

התכנית ניסחה את המשימה כ״שכבת הביטחון → verification_level״, וזו הייתה
הנחה שגויה שלי. `VerificationLevel` מתאר *איך נתון הושג* — raw, ocr,
ai_assisted, human_verified — ולא *כמה בטוח חישוב הזכויות*. שני צירים
שונים. נתוני שכבה א׳ נקראו משכבות GIS רשמיות בלי OCR ובלי אדם, ולכן
`RAW` הוא הערך הנכון היום. הוא יעלה כשצינור התיק יקרא גרמושקה או כשאדם
יאמת — ולכתוב לתוכו ביטחון עכשיו זו אותה טעות קטגורית שכבר נפלנו בה
כשקטגוריית המדיניות נכתבה לשדה שנועד לקטגוריית סינון.
"""
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.cities.herzliya import rights
from app.models.opportunity import Opportunity

# `urban_renewal_compound` אינו נמסר במסלול המגרשי, ועכשיו הוא גם הסטטוס
# של מגרש תפוס. בשני המקרים המשמעות זהה מבחינת המוצר: לא מוכר את זה.
DELIVERABLE = {"eligible", "needs_verification"}


def _threshold_open(checks) -> list[str]:
    """שערי §70א שלא נענו — ״לא ידוע״, לא ״נכשל״."""
    return sorted({c["id"] for c in checks
                   if c["id"] in rights.THRESHOLD_IDS and c["status"] == "unknown"})


async def _store(opp, a) -> None:
    """כותב את תוצאת ההערכה על ההזדמנות. משותף לעיר כולה ולהזדמנות אחת."""
    f = a["floors"]
    opens = _threshold_open(a["checks"])
    renewal = a.get("renewal") or {}
    # ‏W5 · חשד לחידוש: נשאר במסך הצוות, ואינו נמסר ואינו מחויב עד שיוכרע
    review = any(c["status"] == "needs_review" for c in a["checks"])
    opp.metadata_json = {
        **(opp.metadata_json or {}),
        "assessment": {
            "status": a["status"],
            "floors_low": f["low"], "floors_high": f["high"],
            "floors_certain": f["certain"], "case_by_case": f["case_by_case"],
            "cap_400_sqm": a["cap_400_sqm"],
            "cap_400_certainty": a["cap_400_certainty"],
            # ‏W1 · השטח לפי המדיניות, לסינון ולמיון בלי לחשב מעטפת לכל בקשה.
            "policy_area_sqm": ((a.get("policy_area") or {}).get("base") or {}).get("sqm"),
            "policy_share_of_cap": ((a.get("policy_area") or {}).get("base") or {}).get("share_of_cap"),
            # ‏16.09 · אמצע הטווח — השטח שהתרחיש והסריקה מחושבים עליו.
            "policy_mid_sqm": ((a.get("policy_area") or {}).get("mid") or {}).get("sqm"),
            "blocking": sorted({c["id"] for c in a["checks"]
                                if c["status"] in ("failed", "unknown", "routed")}),
            "threshold_open": opens,
            "renewal_status": renewal.get("status"),
            "renewal_reasons": list(renewal.get("reasons") or []),
            "under_review": review,
            # שני דגלים, כי שתי שאלות שונות נשאלו כאן כאחת:
            #
            # ‏`screenable` — נשאר במסלול? יש קומות, לא נפסל, לא נותב.
            #   זה מה שמסך הסינון מציג, וזה מה ש-`deliverable` היה עד כה.
            #
            # ‏`deliverable` — אפשר למסור את זה ללקוח? רק אם תנאי הסף
            #   של §70א **נשאל ונענה**. ‏686 מ-699 מעולם לא נשאלו, כי
            #   הארכיון לא נמשך — והם דווחו כניתנים למסירה. שער שאין לו
            #   מקור פתוח (`UNOBTAINABLE`) אינו חוסם: הוא שאלה פתוחה
            #   בתיק, והסטטוס ממילא needs_verification.
            "screenable": (screenable := a["status"] in DELIVERABLE and f["low"] is not None),
            "deliverable": (screenable and not review
                            and not [i for i in opens if i not in rights.UNOBTAINABLE]),
        },
    }
    flag_modified(opp, "metadata_json")


async def refresh_one(session, rules, opportunity_id) -> dict:
    """הערכה מחדש להזדמנות אחת.

    נדרש ברגע המסירה: אחרי ששולפים תיק בניין עבור לקוח, ההערכה השמורה
    עדיין מחזיקה את התמונה שלפני השליפה. הרצת העיר כולה שם היא בזבוז של
    699 חישובים כדי לעדכן שורה אחת.
    """
    a = await rules.assess(session, opportunity_id)
    opp = await session.get(Opportunity, opportunity_id)
    await _store(opp, a)
    await session.flush()
    return opp.metadata_json["assessment"]


async def refresh(session, rules, city_code: str = "herzliya") -> dict:
    """מריץ assess() על כל ההזדמנויות ושומר את התוצאה. מחזיר פילוח.

    **אינו עושה commit.** הבעלות על הטרנזקציה היא של הקורא. הגרסה הראשונה
    עשתה commit בעצמה, וזה שבר את הבידוד של הבדיקות בלי להיכשל: פיקסטורת
    הבדיקות עוטפת הכול ב-rollback, ו-commit באמצע כבר כתב לבסיס הנתונים
    האמיתי — שתי הזדמנויות סינתטיות נשארו שם אחרי שהסוויטה ״עברה״.
    """
    from collections import Counter
    ids = (await session.execute(
        select(Opportunity.id).where(Opportunity.city_code == city_code))).scalars().all()
    counts = Counter()
    for oid in ids:
        a = await rules.assess(session, oid)
        opp = await session.get(Opportunity, oid)
        await _store(opp, a)
        counts[a["status"]] += 1
        for flag in ("screenable", "deliverable"):
            counts[flag] += 1 if opp.metadata_json["assessment"][flag] else 0
    await session.flush()
    return dict(counts)


async def _main(argv=None):
    """הרצת ההערכה על כל העיר.

    ‏`refresh()` נכתב בלי נקודת כניסה, כך שהתמונה השמורה הייתה תצלום חד-פעמי:
    כל תיקון בשרשרת הזכויות נשאר בקוד ולא הגיע לשורות שהלקוח רואה. עכשיו
    `seed_layer_a` מריץ אותה בסוף הזריעה, וזו הדרך להריץ אותה לבדה.
    """
    import argparse
    from app.cities.herzliya.rules import HerzliyaCityRules
    from app.core.database import AsyncSessionLocal
    ap = argparse.ArgumentParser(description="חישוב מחדש של ההערכה לכל ההזדמנויות")
    ap.add_argument("--city", default="herzliya")
    a = ap.parse_args(argv)
    async with AsyncSessionLocal() as session:
        out = await refresh(session, HerzliyaCityRules(), a.city)
        await session.commit()
        return out


if __name__ == "__main__":
    import asyncio
    print(asyncio.run(_main()))
