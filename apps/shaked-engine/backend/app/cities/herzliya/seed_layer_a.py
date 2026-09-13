"""זריעת מועמדי שכבה א׳ לתוך ה-engine.

‏`POC/layer_a` מסנן את הרצליה כולה — 19,066 חלקות → 904 → 700 — ממקורות
ציבוריים בלבד ובלי פנייה אחת לארכיון. הזורע הזה מעביר את התוצאה לטבלאות
ה-engine: שורת `Opportunity` לכל חלקה, ושורת `FieldEvidence` לכל שדה.

**למה שורת ראיה לכל שדה ולא רק ערך:** ‏`Opportunity` מחזיק
`verification_level` אחד לכל ההזדמנות, וה-PRD דורש מקור, תאריך וודאות לכל
שדה מהותי (‏4.3 · 8.3). שטח מגרש שהגיע מ-GovMap ומספר דירות שהגיע משכבה
עירונית אינם באותה רמת ביטחון, וצריך לראות את ההבדל בתיק.

**אין כאן ערך בלי מקור.** `ev()` דורש מזהה מקור ומיקום; בלעדיהם אין שורה
כלל — לא ניתן לטעון שחיפשנו במקום שאין לו כתובת. כשהמקור קיים והערך אינו
בו, נכתבת שורת `MISSING`: ״נבדק ולא נמצא״ נראה אחרת מ״לא נשאל״, ובלי
ההבחנה הזו תיק שלם נקרא כאילו איש לא בדק. `retrieved_at` מגיע מ-`source_fetched.json`,
כלומר זמן השליפה **האמיתי** של שכבת המקור — לא `now()`, שהיה עובר
ולידציה ומשקר.

הרצה חוזרת מעדכנת ואינה מכפילה: ‏`uq_opportunities_parcel` על
(city, block, block_suffix, parcel) הוא מפתח הישות, והראיות נכתבות מחדש.

    python -m app.cities.herzliya.seed_layer_a [--limit N]
"""
import argparse
import asyncio
import json
import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import AsyncSessionLocal
from app.evidence import Certainty
from app.models.evidence import FieldEvidence
from app.models.opportunity import Opportunity, VerificationLevel

CITY = "herzliya"
LAYER_A = Path(__file__).resolve().parents[6] / "POC" / "layer_a" / "data"

# הקטגוריות כלשונן בעמ׳ 8 של הר/2323. "עירונית" אינו מופיע בתכנית.
CATEGORY = {"9": "התחדשות מגרשית מוטת מגורים",
            "5.5": "התחדשות מגרשית מוטת מגורים נמוכה"}
CEILING = {"9": 9.0, "5.5": 5.5}
K = 0.669                 # מקדם ההמרה מברוטו לשטח נספר. נקודת כיול אחת.

# ערך זקיף בשכבת הכתובות — ספירה שלא נעשתה, לא בניין בן 999 דירות.
UNITS_SENTINEL = 999

# תקרת סבירות ליחס בין השטח הבנוי למספר הדירות, במ״ר לדירה. החציון במלאי
# הוא 94 ואחוזון 90 הוא 166; 200 הוא פי שניים מהחציון, והוא חוסם רק את מה
# שבאמת שבור — 38 חלקות.
MAX_SQM_PER_UNIT = 200.0

# מארח הארכיון העירוני. ראיות שמקורן בו נשלפות לפי דרישת לקוח, אחת-אחת,
# ונשמרות לתמיד — הזריעה אינה נוגעת בהן.
ARCHIVE_HOST = "complot.co.il"
STRENGTHENING = re.compile(r'תמ["״]?א\s*38|חיזוק|רעידות אדמה')


def _load(name: str):
    return json.loads((LAYER_A / name).read_text(encoding="utf-8"))


def usable_units(surv: dict) -> int | None:
    """מספר הדירות הקיים, או None כשהספירה אינה שמישה.

    שני מצבים, ושניהם התגלו כשמיינתי מועמדים לפי גודל ההזדמנות:

    ‏1 · `apt = 999` הוא ערך זקיף בשכבת הכתובות — ספירה שלא נעשתה, לא
        בניין בן 999 דירות. כערך אמיתי הוא מייצר 2,797 יחידות בתמהיל.

    ‏2 · **שכבת נקודות הכתובת מחמיצה כניסות.** אלרואי דוד 32 הוא בניין
        בן 15 קומות על 840 מ״ר טביעת רגל, והוא רשום כארבע דירות; סביר
        שיש בו כ-84. השטח הבנוי נמדד מהגאומטריה ומהימן; מספר הדירות
        מגיע מנקודות כתובת שחלקן חסרות, והוא זה שנשבר. היחס ביניהם
        חושף את זה — חציון 94 מ״ר לדירה, אחוזון 90 הוא 166.

    **מדוע לפסול ולא להשתמש כרף תחתון:** לשער §70א(3) (״לפחות ארבע
    דירות״) ספירה חסרה עדיין מספיקה. אבל אותו מספר מזין את התמהיל
    (×2.8), את החניה ואת פיצוי הדיירים בתחשיב — ושם הוא שגוי פי עשרה
    ומנפח את הרווח. תיק כזה אינו ניתן למסירה.
    """
    units, gross = surv.get("apt"), surv.get("gross")
    if units is None or units >= UNITS_SENTINEL:
        return None
    if gross and (gross * K) / units > MAX_SQM_PER_UNIT:
        return None
    return units


def _rows(key, surv, front, geo, sources, archive):
    """שורות הראיה לחלקה אחת. שדה בלי מקור או מיקום פשוט אינו נוצר."""
    at = f"גוש {key.split('/')[0]} חלקה {key.split('/')[1]}"

    def ev(field, value, source_id, location, certainty=Certainty.OFFICIAL, method=None):
        src = sources.get(source_id)
        # בלי מקור או בלי מיקום אי אפשר אפילו לומר שחיפשנו — אין שורה.
        if not src or not location:
            return None
        # פנינו למקור והערך לא היה שם. זה **ממצא**, לא היעדר: שורת MISSING
        # אומרת ״נבדק ולא נמצא״, ושתיקה אומרת ״לא נשאל״. ‏MISSING אינו
        # ב-DECIDING ולכן לעולם אינו מכריע — הוא רק מונע מהתיק להיראות
        # כאילו השדה מעולם לא עלה.
        if value is None:
            certainty, method = Certainty.MISSING, method or "המקור נבדק והשדה ריק בו"
        return dict(field=field, value=value, certainty=certainty.value,
                    source_url=src["url"], retrieved_at=datetime.fromisoformat(src["retrieved_at"]),
                    # מתי המקור מדווח שהוא עודכן — שונה ממתי אנחנו שלפנו אותו.
                    # שכבת החלקות נושאת SYS_DATE, והוא נע בין 2020 ל-2026.
                    source_updated_at=(geo.get("source_updated_at")
                                       if source_id == "govmap_parcels" else None),
                    location=location, method=method)

    # ── מספר הדירות הקיים: שני מצבים שבהם אי אפשר להשתמש בו ──
    #
    # ‏1 · `apt = 999` הוא ערך זקיף בשכבת הכתובות — ספירה שלא נעשתה, לא
    #     בניין בן 999 דירות. כערך אמיתי הוא מייצר 2,797 יחידות בתמהיל.
    #
    # ‏2 · **שכבת נקודות הכתובת מחמיצה כניסות.** אלרואי דוד 32 הוא בניין
    #     בן 15 קומות על 840 מ״ר טביעת רגל, והוא רשום כארבע דירות; סביר
    #     שיש בו כ-84. השטח הבנוי נמדד מהגאומטריה ומהימן; מספר הדירות
    #     מגיע מנקודות כתובת שחלקן חסרות, והוא זה שנשבר.
    #
    #     היחס בין השניים חושף את זה: החציון במלאי 94 מ״ר לדירה, אחוזון
    #     90 הוא 166. מעל `MAX_SQM_PER_UNIT` הספירה אינה שמישה.
    #
    # **מדוע לפסול ולא להשתמש כרף תחתון:** לשער §70א(3) (״לפחות ארבע
    # דירות״) ספירה חסרה עדיין מספיקה. אבל אותו מספר מזין את התמהיל
    # (×2.8), את החניה ואת פיצוי הדיירים בתחשיב — ושם הוא שגוי פי עשרה,
    # ומנפח את הרווח. תיק שכזה אינו ניתן למסירה, ולכן הספירה אינה נכתבת.
    units = usable_units(surv)
    gross = surv.get("gross")
    estimate = round(gross * K, 1) if gross else None

    cat = str(surv.get("cat"))
    out = [
        ev("parcel_area", surv.get("lot"), "govmap_parcels", f"{at} · LEGAL_AREA", method="WFS"),
        ev("units", units, "agol_addresses",
           f'{at} · {surv.get("entrances")} כניסות', method="סכום num_aprt בנקודות הכתובת בחלקה"),
        ev("floors", surv.get("floors"), "agol_buildings", at,
           method="מקסימום Num_floors על המבנים בחלקה"),
        ev("renewal_policy_category", CATEGORY.get(cat), "strategic_plan",
           f"{at} · עמ׳ 8", Certainty.DERIVED,
           "דגימת דיסק 15 מ׳ במפה שגאו-רפרנסה, התאמת צבע קרובה, הכרעת רוב"),
        ev("category_ceiling", CEILING.get(cat), "strategic_plan", f"{at} · עמ׳ 8", Certainty.DERIVED),
        ev("street_width", front.get("width"), "govmap_parcels",
           f'{at} · {front.get("why", "")}'[:400], Certainty.DERIVED,
           "פער קדסטרלי, החזית הצרה קובעת; אמין עד 15 מ׳"),
        ev("pilotis", surv.get("pilotis"), "agol_addresses", f"{at} · amudim"),
        ev("registration_area", geo.get("registration_area"), "strategic_plan",
           f"{at} · אזורי רישום", Certainty.DERIVED, "אזור הרישום שמכיל את מרכז החלקה"),
        # השער הראשון של §70א: ״מגרש המיועד לפי תכנית **גם** למגורים״.
        # נגזר מפוליגוני ייעוד הקרקע בתכניות המקומיות (504-*) ב-XPlan.
        ev("residential_zoning", geo.get("residential_zoning"), "iplan_xplan",
           f"{at} · ייעוד קרקע בתכנית מקומית", Certainty.DERIVED,
           "חפיפה של מעל 30% עם פוליגון ייעוד שבשמו 'מגורים'"),
        ev("in_tama70", geo.get("in_tama70"), "iplan_xplan", at, Certainty.DERIVED,
           'חפיפה של מעל 50% משטח החלקה עם מרחב תמ"א 70'),
        ev("scope_buildings", geo.get("buildings"), "agol_buildings", at, Certainty.DERIVED,
           "מבנים שרוב שטחם בתוך החלקה"),
        # ‏k=0.669 כויל על נקודת אמת אחת, ולכן ESTIMATE ולא DERIVED. ההבדל אינו
        # סמנטי: הערך מוכפל פי ארבע כדי להגיע לתקרת הזכויות, ו-ESTIMATE נשאר
        # מחוץ ל-DECIDING כך שאפשר להציג אותו ואי אפשר להכריע לפיו.
        ev("existing_area", estimate,
           "agol_buildings", f'{at} · ברוטו {gross} מ"ר', Certainty.ESTIMATE,
           f"טביעת רגל × קומות × k={K} · k כויל על היתר 19780028, נקודת אמת אחת"),
    ]

    if archive:
        years = [int(str(r["req"])[:4]) for r in archive if str(r.get("req", ""))[:4].isdigit()]
        loc = f"{at} · {len(archive)} בקשות בתיק הבניין"
        if years:
            out.append(ev("permit_date", f"{min(years)}-01-01", "archive", loc,
                          Certainty.DERIVED, "שנת הבקשה המוקדמת ביותר בתיק"))
        hits = [r for r in archive if STRENGTHENING.search(r.get("action") or "")]
        # חיזוק **עם** היתר פוסל לפי §70א(2). חיזוק **בלי** היתר פירושו
        # שיזם אחר כבר מול הדיירים — כשיר בדין, לא זמין בפועל. שני שדות.
        out.append(ev("strengthened", any((r.get("permit_date") or "").strip() for r in hits),
                      "archive", loc, Certainty.DERIVED))
        out.append(ev("occupied", any(not (r.get("permit_date") or "").strip() for r in hits),
                      "archive", loc, Certainty.DERIVED,
                      "בקשת חיזוק שהוגשה ולא הופק לה היתר"))
        # ‏§70ב(א)(1)(ב): תוספת שהותרה אחרי 18.5.2005 אינה נכנסת לבסיס
        # ה-400%. התיק מדווח שהיתר ניתן, לא כמה מ״ר הוא הוסיף, ולכן הערך
        # בוליאני: **False** פירושו נבדק ואין, ולא ״לא נבדק״ — את ההבדל
        # הזה `cap_400` מטפל בו, ואת ההיעדר כשאין תיק כלל.
        out.append(ev("post_2005_permit", _post_2005(archive), "archive", loc,
                      Certainty.DERIVED, "היתר בתיק שתאריכו אחרי 18.5.2005"))
    return [r for r in out if r]


CUTOFF_2005 = date(2005, 5, 18)


def _post_2005(requests) -> bool:
    """האם בתיק היתר שניתן אחרי מועד החיתוך של §70ב(א)(1)(ב)."""
    for r in requests:
        raw = (r.get("permit_date") or "").strip()
        try:
            d, m, y = (int(x) for x in raw.split("/"))
        except ValueError:
            continue
        if date(y, m, d) > CUTOFF_2005:
            return True
    return False


async def seed(limit=None):
    surv = {x["key"]: x for x in _load("survivors_apt.json")}
    front = {x["key"]: x for x in _load("frontages.json")}
    geo = _load("parcels_700.geojson.json")
    sources = _load("source_fetched.json")
    facts = {f["tik"]: f for f in _load("archive_facts.json")}
    ptik = _load("parcel_tiks.json")

    keys = [k for k in surv if k in geo][: limit or None]
    written = skipped = evidence_rows = 0

    async with AsyncSessionLocal() as session:
        for key in keys:
            g = geo[key]
            if not g.get("address"):
                skipped += 1           # address הוא NOT NULL; אין להמציא כתובת
                continue
            block, parcel = key.split("/")
            geom = json.dumps(g["geometry"])

            stmt = (
                insert(Opportunity)
                .values(city_code=CITY, address=g["address"], block=block, block_suffix=0,
                        parcel=parcel,
                        geom=f"SRID=4326;{_wkt(g['geometry'])}",
                        area_sqm=surv[key].get("lot"),
                        # הערך המנופה, ולא הגולמי: העמודה מזינה את התחשיב
                        # הכלכלי בתיק ואת המיון במסך, ומספר שפסלנו כלא
                        # שמיש אינו יכול להמשיך לעבוד דרך הדלת האחורית.
                        existing_units=usable_units(surv[key]),
                        verification_level=VerificationLevel.RAW.value,
                        metadata_json=_metadata(key, surv[key], front.get(key, {})))
                .on_conflict_do_update(
                    index_elements=["city_code", "block", "block_suffix", "parcel"],
                    index_where=Opportunity.__table__.c.block.isnot(None) & Opportunity.__table__.c.parcel.isnot(None),
                    # metadata_json חייב להתעדכן גם הוא — בלעדיו הרצה חוזרת
                    # משאירה שורה ישנה עם ערך שכבר תוקן, וזה נראה כמו כישלון תיקון.
                    set_=dict(address=g["address"], area_sqm=surv[key].get("lot"),
                              # הערך המנופה, ולא הגולמי: העמודה מזינה את התחשיב
                        # הכלכלי בתיק ואת המיון במסך, ומספר שפסלנו כלא
                        # שמיש אינו יכול להמשיך לעבוד דרך הדלת האחורית.
                        existing_units=usable_units(surv[key]),
                              metadata_json=_metadata(key, surv[key], front.get(key, {}))))
                .returning(Opportunity.id)
            )
            opp_id = (await session.execute(stmt)).scalar_one()

            archive = []
            for t in ptik.get(key, []):
                if t in facts:
                    archive += facts[t].get("requests", [])

            # **אין למחוק ראיות שנשלפו מהארכיון לפי דרישה.**
            #
            # הזריעה כותבת מחדש את מה שהיא מייצרת מהקבצים המקומיים, ועד
            # כה מחקה את *כל* הראיות של ההזדמנות. תיק בניין שנשלף עבור
            # לקוח — שליפה יקרה, מוגבלת בקצב, ושמדיניות הסיכון מחייבת
            # לשמור אותה **לתמיד** — נמחק בזריעה הבאה בלי סימן.
            #
            # קרה בפועל: ארבעה תיקים שנשלפו להדגמה נמחקו בזריעה שאחריה,
            # ומספר המועמדים המוכנים ירד מ-9 ל-5.
            #
            # אם התיק כבר בקובץ המקומי, השורה החדשה תדרוס אותו ממילא —
            # ולכן הסינון הוא על המקור ולא על השדה.
            await session.execute(
                delete(FieldEvidence).where(
                    FieldEvidence.opportunity_id == opp_id,
                    FieldEvidence.source_url.not_like(f"%{ARCHIVE_HOST}%"),
                )
            )
            rows = _rows(key, surv[key], front.get(key, {}), g, sources, archive)
            for r in rows:
                session.add(FieldEvidence(opportunity_id=opp_id, **r))
            evidence_rows += len(rows)
            written += 1

        await session.commit()
    return {"written": written, "skipped_no_address": skipped, "evidence_rows": evidence_rows}


def _metadata(key, surv, front):
    """‏`category` כאן הוא **קטגוריית הסינון של ה-engine**, לא קטגוריית מפת
    המדיניות. שני הדברים נשאו את אותו שם ולכן הראשונה נדרסה בשקט בזריעה
    הראשונה, וכל 699 השורות נעלמו מה-API בלי הודעת שגיאה.

    המיפוי: מועמדי שכבה א׳ עברו סינון חזק יותר משל XPlan — קטגוריית מפת
    מדיניות, לא מבנה לשימור, ≥2 קומות, ≥4 דירות. מי שגם רוחב הרחוב שלו
    נמדד יכול להפיק מספר קומות ולכן `primary_candidate`; מי שלא —
    `needs_verification`, וזה מדויק ולא הנחה.
    """
    measured = front.get("width") is not None
    return {
        "source": "layer_a",
        "category": "primary_candidate" if measured else "needs_verification",
        "category_basis": "סינון שכבה א׳: מפת מדיניות, שימור, קומות, דירות"
                          + ("" if measured else " · רוחב רחוב לא נמדד"),
        "renewal_policy_category": CATEGORY.get(str(surv.get("cat"))),
        "category_ceiling": CEILING.get(str(surv.get("cat"))),
    }


def _wkt(geom):
    """GeoJSON → WKT. MultiPolygon בלבד, כפי שהעמודה מצהירה."""
    def ring(r):
        return "(" + ",".join(f"{x:.7f} {y:.7f}" for x, y, *_ in r) + ")"
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        raise ValueError(f'גאומטריה לא נתמכת: {geom["type"]}')
    return "MULTIPOLYGON(" + ",".join("(" + ",".join(ring(r) for r in p) + ")" for p in polys) + ")"


async def _seed_and_assess(limit=None):
    """זריעה ואז הערכה. ‏**חייבות לרוץ יחד.**

    הראיות וההערכה השמורה הם אותה אמת בשתי צורות. זריעה לבדה מחליפה את
    הראיות ומשאירה `metadata_json.assessment` מהריצה הקודמת — ואז המסך
    מציג סטטוס שחושב על נתונים שכבר אינם שם, בלי שגיאה ובלי סימן.
    """
    from app.cities.herzliya.assessments import refresh
    from app.cities.herzliya.rules import HerzliyaCityRules
    out = await seed(limit)
    async with AsyncSessionLocal() as session:
        out["assessment"] = await refresh(session, HerzliyaCityRules())
        await session.commit()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-assess", action="store_true",
                    help="זריעה בלבד — ההערכה השמורה תישאר מהריצה הקודמת")
    a = ap.parse_args()
    print(asyncio.run(seed(a.limit) if a.no_assess else _seed_and_assess(a.limit)))
