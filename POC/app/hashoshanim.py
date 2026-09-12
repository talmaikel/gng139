"""Evidence-backed pilot dossier for Hashoshanim 4, Herzliya."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from shapely.geometry import shape

from .config import DATA, POLICY_URL, RULE_VERSION, TEMPLATE_VERSION
from .documents import archive_tables
from .geo import wgs
from .rules import evaluate, evidence
from .sources import utcnow


BASE = DATA / "verification" / "hashoshanim-4"


def _json(name):
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def _source_for_path(path, url):
    timestamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return {
        "url": url,
        "retrieved_at": timestamp,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "local_evidence": str(path),
    }


def _source_for_file(name, url):
    return _source_for_path(BASE / name, url)


def _field(value, source, certainty, location, method, **extra):
    item = evidence(value, source, certainty, location, method)
    item.update(extra)
    return item


def build_hashoshanim_dossier():
    archive = _json("archive.json")
    parcel = _json("current-parcel.json")[0]
    building = _json("current-buildings.json")[0]
    # The manifest is written on Windows, so its paths carry "\\" separators that
    # Path() does not split on POSIX. Normalise before taking the stem, or every
    # document key comes out as the whole path and the dossier cannot be built.
    documents = {PurePosixPath(item["path"].replace("\\", "/")).stem: item
                 for item in _json("document-manifest.json")}

    archive_source = archive["files"][0]["source"]
    parcel_source = parcel["_source"]
    building_source = building["_source"]
    plan_1970 = documents["1970-plan"]["source"]
    permit_1970 = documents["1970-permit"]["source"]
    plan_2013 = documents["2013-plan"]["source"]
    permit_2013 = documents["2013-permit"]["source"]
    xplan_plans = _source_for_file(
        "xplan-at-address.json",
        "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer/1/query",
    )
    xplan_landuse = _source_for_file(
        "xplan-landuse-at-address.json",
        "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer/4/query",
    )
    policy_source = _source_for_path(DATA / "verification" / "policy_pdf.txt", POLICY_URL)

    residential_main = 3 * 187.97
    permitted_stair = 14.68
    legal_base_above_ground = residential_main + permitted_stair
    residential_share = residential_main / legal_base_above_ground
    cap_area = legal_base_above_ground * 4

    fields = {
        "address": _field("השושנים 4, הרצליה", archive_source, "official", "כותרת תיק בניין 5848", "HTML label extraction"),
        "eligibility_summary": _field(
            "עבר 6 מתוך 6 תנאי סף של המבנה; נדרשת השלמת בדיקה תכנונית",
            policy_source,
            "derived",
            "יישום תנאי הסף במדיניות על נתוני היתרים ותיק 5848",
            "versioned rule evaluation",
        ),
        "building_file_number": _field(5848, archive_source, "official", "כותרת תיק הבניין", "structured archive record"),
        "gush": _field(6529, archive_source, "official", "טבלת גושים וחלקות", "structured archive record"),
        "parcel": _field(167, archive_source, "official", "טבלת גושים וחלקות", "structured archive record"),
        "parcel_area": _field(
            704,
            parcel_source,
            "official",
            "Parcels_ITM.785443.LEGAL_AREA",
            "GovMap WFS",
            note="שכבת GovMap מציינת שהשטח הרשום אינו אסמכתה משפטית; שטח הגאומטריה הוא 688.93 מ״ר.",
        ),
        "footprint_area": _field(
            round(shape(building["geometry"]).area, 2),
            building_source,
            "community",
            "OSM way 385608705 geometry",
            "ITM polygon area",
        ),
        "units": _field(
            6,
            plan_1970,
            "manually_verified",
            "תכנית היתר 1970, טבלת דירות; מאומת גם בהיתר 2013 עמ׳ 1",
            "full-page visual review",
            corroboration=[permit_2013["url"]],
        ),
        "floors": _field(
            4,
            plan_1970,
            "manually_verified",
            "תכנית היתר 1970: 3 קומות מגורים מעל קומת עמודים; המדיניות מונה קומת עמודים",
            "full-page visual review and policy interpretation",
        ),
        "floor_configuration": _field(
            "3 קומות מגורים מעל קומת עמודים מפולשת",
            permit_2013,
            "official",
            "היתר 2013 עמ׳ 1, מהות ההיתר",
            "full-page visual review",
        ),
        "permit_date": _field("1970-04-12", archive_source, "official", "טבלת בקשות: היתר 99", "structured archive record"),
        "original_permit_number": _field(99, permit_1970, "manually_verified", "היתר 1970 עמ׳ 1", "full-page visual review"),
        "strengthened": _field(
            False,
            archive_source,
            "manually_verified",
            "רשימת שתי הבקשות בתיק 5848 ובדיקת מסמכי 1970 ו-2013",
            "complete displayed request-list and permit review",
            note="היתר 2013 עוסק במעלית, מדרגות, לובי וחדר אשפה; לא נמצא היתר חיזוק סיסמי בתיק.",
        ),
        "engineer_opinion": _field(
            "לא נדרש להוכחת תנאי הגיל (היתר לפני 1980)",
            policy_source,
            "derived",
            "מדיניות חלופת שקד, תנאי מבנה טעון חיזוק",
            "policy rule application",
        ),
        "residential_zoning": _field(True, archive_source, "official", "תכנית 1192 — מגורים ב׳", "structured archive record"),
        "zoning_designation": _field("מגורים ב׳", archive_source, "official", "טבלת תכניות בתיק 5848", "structured archive record"),
        "residential_share": _field(
            round(residential_share, 4),
            plan_1970,
            "derived",
            "563.91 מ״ר מגורים מתוך בסיס על-קרקעי שמרני של 578.59 מ״ר",
            "permit-area calculation",
        ),
        "main_residential_area": _field(round(residential_main, 2), plan_1970, "manually_verified", "טבלת שטחים: 3 × 187.97", "permit-area calculation"),
        "stair_area": _field(permitted_stair, plan_1970, "manually_verified", "טבלת חלקי בניין אחרים — חדר מדרגות", "full-page visual review"),
        "open_pilotis_area": _field(148.50, plan_1970, "manually_verified", "טבלת שטחים — קומת עמודים", "full-page visual review"),
        "shelter_area": _field(21.00, plan_1970, "manually_verified", "טבלת חלקי בניין אחרים — מקלט", "full-page visual review"),
        "original_permitted_total_area": _field(748.09, plan_1970, "manually_verified", "סך הכול בטבלת השטחים", "full-page visual review"),
        "post_2005_addition_area": _field(7.87, permit_2013, "official", "היתר 2013 עמ׳ 1 — שטחי שירות", "full-page visual review"),
        "existing_legal_area": _field(
            round(legal_base_above_ground, 2),
            plan_1970,
            "manually_verified",
            "563.91 מ״ר מגורים + 14.68 מ״ר חדר מדרגות; עמודים מפולשים ומקלט תת-קרקעי הוחרגו",
            "conservative Shaked-policy base calculation",
        ),
        "shaked_area_cap": _field(
            round(cap_area, 2),
            policy_source,
            "derived",
            "מדיניות עמ׳ 3–4: סך שטח מעל הקרקע עד 400% × בסיס היתר 578.59 מ״ר",
            "policy ceiling calculation",
        ),
        "indicative_unit_range": _field(
            "17–19",
            policy_source,
            "derived",
            "מדיניות עמ׳ 6: מכפיל 2.8–3.18 × 6 דירות; עיגול ליחידות שלמות טעון אישור",
            "policy density calculation",
        ),
        "indicative_additional_units": _field(
            "11–13",
            policy_source,
            "derived",
            "טווח 17–19 פחות 6 דירות קיימות",
            "arithmetic",
        ),
        "additional_balcony_area": _field(
            "204–228 מ״ר",
            policy_source,
            "derived",
            "ממוצע מרפסות מרבי 12 מ״ר × 17–19 דירות",
            "policy ceiling calculation",
        ),
        "tama70_zone": _field(
            "מרחב עירוני מוטה מטרו — תא שטח 206",
            xplan_landuse,
            "official",
            "Xplan land-use feature at parcel centroid",
            "ArcGIS point intersection",
        ),
        "planning_lot": evidence(None),
        "planning_basis": evidence(None),
        "overriding_plans_checked": evidence(None),
    }

    checks = evaluate(fields, {})
    core_ids = {"residential_zoning", "residential_share", "permit_date", "strengthened", "floors", "units"}
    core_checks = [item for item in checks if item["id"] in core_ids]
    rights_analysis = {
        "status": "preliminary_ceiling",
        "route": "הריסה ובנייה מחדש",
        "base_area_m2": round(legal_base_above_ground, 2),
        "base_formula": "3 × 187.97 + 14.68",
        "excluded_from_base": [
            {"label": "קומת עמודים מפולשת", "area_m2": 148.50},
            {"label": "מקלט תת-קרקעי", "area_m2": 21.00},
            {"label": "תוספת לאחר 18.05.2005", "area_m2": 7.87},
        ],
        "maximum_total_above_ground_m2": round(cap_area, 2),
        "area_formula": "578.59 × 400%",
        "existing_units": 6,
        "unit_multiplier_range": [2.8, 3.18],
        "calculated_unit_range": [16.8, 19.08],
        "indicative_whole_unit_range": [17, 19],
        "indicative_additional_units": [11, 13],
        "additional_balcony_area_m2": [204, 228],
        "height": None,
        "public_area_at_full_cap_m2": round(cap_area * 0.10, 2),
        "note": "התקרה כפופה לשיקול דעת הוועדה, לתמ״א 70, למפת המדיניות, לגובה ולנפח האפשריים, לתכניות תקפות ולבדיקת מידע תכנוני רשמי.",
    }
    gaps = [
        "לא זוהה מספר מגרש תכנוני; חלקה קדסטרית אינה תחליף למגרש תכנוני.",
        "תמ״א 70 חלה ומסווגת את הנקודה כמרחב עירוני מוטה מטרו; נדרשת בדיקת הוראות מלאה ואישור העירייה למסלול מגרשי.",
        "סיווג החלקה במפת ההתחדשות וגובה הבינוי המותר לא אומתו בשכבה גאוגרפית ברמת חלקה.",
        "שטח 704 מ״ר ב-GovMap נושא הסתייגות; נדרשים נסח רישום ומפת מדידה עדכנית לשטח מחייב.",
        "ההיתרים מוכיחים את המאושר, אך לא נבדקו חריגות בנייה, תשריט בית משותף או מצב בנוי עדכני.",
        "טרם הושלמה בדיקה סטטוטורית של כל התכניות התקפות, הר/2530 שבתהליך, הפקעות, קווי בניין וחניה.",
        "לא הוגדרו הנחות כלכליות ושמאיות מאושרות; לכן לא חושב רווח יזמי.",
    ]
    archive_records = [{
        "id": archive["files"][0]["id"],
        "source": archive_source,
        "tables": archive_tables(archive["files"][0]["html"]),
    }]
    parcel_row = {
        "id": "parcel:6529:0:167",
        "gush": 6529,
        "suffix": 0,
        "parcel": 167,
        "overlap": 1.0,
        "geometry": wgs(shape(parcel["geometry"])),
        "source": parcel_source,
    }
    dossier = {
        "building_id": "municipal-file:5848",
        "entity_keys": [parcel_row["id"]],
        "status": "needs_verification",
        "eligibility": {
            "status": "core_thresholds_passed_planning_review_required",
            "core_passed": len(core_checks) == 6 and all(item["status"] == "passed" for item in core_checks),
            "passed_count": sum(item["status"] == "passed" for item in core_checks),
            "total_core_checks": 6,
            "conclusion": "תנאי הסף של המבנה עוברים; הזכאות הסופית והיקף המימוש תלויים בבדיקה תכנונית משלימה.",
        },
        "fields": fields,
        "geometry": wgs(shape(building["geometry"])),
        "parcels": [parcel_row],
        "checks": checks,
        "gaps": gaps,
        "source_issues": [],
        "archive_records": archive_records,
        "documents": [
            {"id": key, "source": item["source"], "pages": 1 if "plan" in key else 2, "path": item["path"]}
            for key, item in documents.items()
        ],
        "applicable_online_plans": [
            "504-0760520", "504-0273037", "504-0336685", "תמ״א 60", "תמ״א 70", "504-0113134"
        ],
        "online_plans_source": xplan_plans,
        "rights_analysis": rights_analysis,
        "scenario": None,
        "rule_version": RULE_VERSION,
        "template_version": TEMPLATE_VERSION,
        "policy_source": POLICY_URL,
        "created_at": utcnow(),
        "building_source": building_source,
        "selection_note": "ניסוי ממוקד: זהות הבניין אומתה מול תיק 5848 וחלקה 167. טביעת המבנה במפה היא מ-OpenStreetMap.",
    }
    stable = dict(dossier)
    stable.pop("created_at")
    dossier["id"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]
    return dossier


def import_hashoshanim(store):
    dossier = build_hashoshanim_dossier()
    store.save_dossier(dossier)
    return store.dossier(dossier["id"])
