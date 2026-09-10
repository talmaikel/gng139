"""Reproducible evidence-backed dossiers from the saved three-file pilot batch."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from shapely.geometry import shape

from .config import DATA, POLICY_URL, RULE_VERSION, TEMPLATE_VERSION
from .documents import archive_tables
from .geo import wgs
from .rules import evidence, evaluate
from .sources import utcnow

BASE = DATA / "pilot-batch-01"

CASES = {
    "19610028": {
        "address": "בר-כוכבא 12, הרצליה", "file": 1652, "gush": 6424, "parcel": 83,
        "permit": 3604, "permit_date": "1961-10-12", "zoning": "מגורים א' מוגבל",
        "use": "בית מגורים קוטג'", "pdf": "19610028-plan.pdf",
    },
    "19650106": {
        "address": "הרב קוק 10, הרצליה", "file": 4461, "gush": 6538, "parcel": 206,
        "permit": 276, "permit_date": "1965-11-24", "zoning": "מגורים ב",
        "use": "בית מגורים משותף", "pdf": "19650106-plan.pdf",
        "ocr_candidates": {
            "units": (7, "p1-r1-c12", "טבלת הדירות בתכנית; הספרה 7 דורשת אישור אנושי"),
            "floors": (3, "p1-r1-c12", "שלוש שורות קומות מגורים נראות בטבלה; הגדרת הקומות דורשת אישור"),
            "floor_configuration": ("3 קומות מגורים", "p1-r1-c12", "פענוח ראשוני של טבלת הקומות"),
            "main_residential_area": (187.47, "p1-r1-c10", "סיכום עמודת השטח העיקרי בטבלת השטחים"),
            "service_area": (59.71, "p1-r1-c10", "סיכום עמודת שטחי השירות בטבלת השטחים"),
            "original_permitted_total_area": (247.18, "p1-r1-c10", "סיכום השטח הכולל בטבלת השטחים"),
        },
    },
}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _field(value, source, certainty, location, method, **extra):
    row=evidence(value,source,certainty,location,method);row.update(extra);return row


def _core_summary(checks):
    ids={"residential_zoning","residential_share","permit_date","strengthened","floors","units"}
    core=[row for row in checks if row["id"] in ids]
    passed=sum(row["status"]=="passed" for row in core)
    return passed,len(core)


def build_pilot_dossier(request_id, *, pipeline_run_id=None):
    request_id=str(request_id); case=CASES[request_id]
    source_record=_read(BASE/"source-records"/f"{request_id}.json")
    request_record=_read(DATA/"verification"/"permits"/f"{request_id}.json")
    parcels=_read(BASE/"parcel-evidence.json")
    parcel=parcels[f"{case['gush']}-{case['parcel']}"][0]
    pdf_path=BASE/"input"/case["pdf"]
    pdf_source=dict(source_record["pdf"],local_evidence=str(pdf_path))
    archive_source=dict(source_record["request_page"],local_evidence=str(DATA/"verification"/"permits"/f"{request_id}.json"))
    parcel_source=dict(parcel["_source"],source_updated_at=parcel["properties"].get("SYS_DATE"))
    fields={key:evidence(None) for key in [
        "units","floors","strengthened","engineer_opinion","residential_share","scope_buildings",
        "renewal_policy_category","planning_lot","planning_basis","overriding_plans_checked","existing_legal_area",
    ]}
    fields.update({
        "address":_field(case["address"],archive_source,"official","כותרת בקשה ציבורית","structured public-page extraction"),
        "building_file_number":_field(case["file"],archive_source,"official","פרטי תיק בניין","structured public-page extraction"),
        "gush":_field(case["gush"],archive_source,"official","טבלת גוש וחלקה","structured public-page extraction"),
        "parcel":_field(case["parcel"],archive_source,"official","טבלת גוש וחלקה","structured public-page extraction"),
        "parcel_area":_field(parcel["properties"]["LEGAL_AREA"],parcel_source,"official",parcel["id"]+".LEGAL_AREA","GovMap WFS",note="נתון GovMap כולל הסתייגות ואינו תחליף לנסח רישום"),
        "permit_date":_field(case["permit_date"],archive_source,"official","פרטי היתר בבקשה הציבורית","structured public-page extraction"),
        "original_permit_number":_field(case["permit"],archive_source,"official","מספר היתר בבקשה הציבורית","structured public-page extraction"),
        "residential_zoning":_field(True,archive_source,"official",f"ייעוד: {case['zoning']}","structured public-page extraction"),
        "zoning_designation":_field(case["zoning"],archive_source,"official","טבלת גוש וחלקה","structured public-page extraction"),
        "building_use":_field(case["use"],archive_source,"official","שימוש עיקרי","structured public-page extraction"),
        "scope_parcels":_field(1,parcel_source,"derived","שיוך התיק לגוש ולחלקה יחידים","record linkage"),
    })
    for key,(value,tile,note) in case.get("ocr_candidates",{}).items():
        fields[key]=_field(value,pdf_source,"ocr_candidate",f"תכנית סרוקה, עמוד 1, tile {tile}","Tesseract OCR plus visual candidate review",note=note)
    checks=evaluate(fields,{})
    passed,total=_core_summary(checks)
    gaps=[row["label"] for row in checks if row["status"]=="unknown"]
    gaps += [
        "נדרש אימות אנושי של כל ערכי ה-OCR לפני שימוש בתנאי הסף.",
        "טביעת המבנה המדויקת לא אותרה; נקודת המפה היא מרכז החלקה הרשמית.",
        "טרם הושלמו בדיקת תיק הבניין המלא, תכניות גוברות, מגרש תכנוני וזכויות מפורטות.",
        "אין בסיס מאומת לתרחיש זכויות או לחישוב כלכלי.",
    ]
    parcel_row={
        "id":f"parcel:{case['gush']}:0:{case['parcel']}","gush":case["gush"],"suffix":0,
        "parcel":case["parcel"],"overlap":None,"geometry":wgs(shape(parcel["geometry"])),"source":parcel_source,
    }
    page_count=0
    with pymupdf.open(pdf_path) as doc:page_count=doc.page_count
    dossier={
        "building_id":f"municipal-file:{case['file']}","entity_keys":[parcel_row["id"]],
        "status":"needs_verification","eligibility_status":"needs_verification",
        "eligibility":{"status":"core_evidence_incomplete","core_passed":False,"passed_count":passed,"total_core_checks":total,
                       "conclusion":f"{passed} מתוך {total} תנאי סף הוכחו; יתר התנאים נשארו לאימות."},
        "fields":fields,"geometry":wgs(shape(parcel["geometry"]).centroid),"parcels":[parcel_row],"checks":checks,
        "gaps":list(dict.fromkeys(gaps)),"source_issues":[],
        "archive_records":[{"id":str(case["file"]),"source":archive_source,"tables":archive_tables(request_record["html"])}],
        "documents":[{"id":f"{request_id}-plan","source":pdf_source,"pages":page_count,"path":str(pdf_path)}],
        "scenario":None,"rights_analysis":None,"rule_version":RULE_VERSION,"template_version":TEMPLATE_VERSION,
        "policy_source":POLICY_URL,"created_at":utcnow(),"building_source":parcel_source,
        "selection_note":"תיק פיילוט שנבנה ממסמך ההיתר השמור, מטא-דאטה עירוני וחלקת GovMap. כל ממצא מהסריקה הוכנס כמועמד OCR הדורש אימות אנושי. נקודת המבנה נגזרה ממרכז החלקה.",
        "pipeline_run_id":pipeline_run_id,
    }
    stable=dict(dossier);stable.pop("created_at");stable.pop("pipeline_run_id",None)
    dossier["id"]=hashlib.sha256(json.dumps(stable,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
    return dossier
