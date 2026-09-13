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

from app.models.opportunity import Opportunity

DELIVERABLE = {"eligible", "needs_verification"}


async def refresh(session, rules, city_code: str = "herzliya") -> dict:
    """מריץ assess() על כל ההזדמנויות ושומר את התוצאה. מחזיר פילוח."""
    from collections import Counter
    ids = (await session.execute(
        select(Opportunity.id).where(Opportunity.city_code == city_code))).scalars().all()
    counts = Counter()
    for oid in ids:
        a = await rules.assess(session, oid)
        opp = await session.get(Opportunity, oid)
        f = a["floors"]
        opp.metadata_json = {
            **(opp.metadata_json or {}),
            "assessment": {
                "status": a["status"],
                "floors_low": f["low"], "floors_high": f["high"],
                "floors_certain": f["certain"], "case_by_case": f["case_by_case"],
                "cap_400_sqm": a["cap_400_sqm"],
                "cap_400_certainty": a["cap_400_certainty"],
                "blocking": sorted({c["id"] for c in a["checks"]
                                    if c["status"] in ("failed", "unknown", "routed")}),
                "deliverable": a["status"] in DELIVERABLE and f["low"] is not None,
            },
        }
        flag_modified(opp, "metadata_json")
        counts[a["status"]] += 1
        counts["deliverable"] += 1 if opp.metadata_json["assessment"]["deliverable"] else 0
    await session.commit()
    return dict(counts)
