"""Collect public building files for parcels around Hashoshanim 4 and build timed dossiers for them."""
import argparse
import hashlib
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from shapely.geometry import Point,shape

from app.archive_catalog import parse_building_file
from app.config import DATA
from app.documents import archive_tables
from app.local_ocr import extract_local
from app.pilot_dossiers import build_case_dossier
from app.sources import ARCHIVE,BuildingArchive,GovMap,PublicClient,SourceError,text_from_html,utcnow
from app.store import Store

BATCH=DATA/"pilot-batch-02-hashoshanim"
PERMITS=DATA/"verification"/"permits"
ANCHOR={"label":"השושנים 4 הרצליה","gush":6529,"parcel":167,"itm":(185019.62,675065.69)}
MIN_PARCEL_AREA=150

LABELS=["מספר הבקשה","כתובת","תאריך הגשה","מספר תיק בניין","סוג הבקשה","שימוש עיקרי","תיאור הבקשה","מספר היתר","תאריך הפקת היתר","שטח עיקרי","שטח שירות","סך מספר יחידות דיור המבוקשות"]


def log(message):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}",flush=True)


def iso_date(value):
    match=re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})",(value or "").strip())
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else None


def parse_request_page(html):
    lines=[x.strip() for x in text_from_html(html).splitlines()];lines=[x for x in lines if x]
    labelled={}
    for index,line in enumerate(lines):
        key=line.rstrip(":")
        if key in LABELS and key not in labelled and index+1<len(lines):
            value=lines[index+1]
            labelled[key]=None if value.rstrip(":") in LABELS else value
    designations=[]
    for table in archive_tables(html):
        headers=[x.replace("‏","").strip() for x in table["headers"]]
        if "מספר גוש" in headers and "יעוד" in headers:
            zi=headers.index("יעוד")
            designations+=[row[zi].strip() for row in table["rows"] if len(row)>zi and row[zi].strip()]
    # A parcel can carry several rows (e.g. a road strip plus residential); keep all of them.
    zoning=" / ".join(dict.fromkeys(designations)) or None
    def number(text):
        match=re.search(r"\d+(?:\.\d+)?",text or "")
        return float(match.group()) if match else None
    return {"address":labelled.get("כתובת"),"submitted":iso_date(labelled.get("תאריך הגשה")),"request_type":labelled.get("סוג הבקשה"),
            "use":labelled.get("שימוש עיקרי"),"description":labelled.get("תיאור הבקשה"),"permit":labelled.get("מספר היתר"),
            "permit_date":iso_date(labelled.get("תאריך הפקת היתר")),"main_area":number(labelled.get("שטח עיקרי")),
            "service_area":number(labelled.get("שטח שירות")),"units_requested":number(labelled.get("סך מספר יחידות דיור המבוקשות")),"zoning":zoning}


def fetch_plan_pdf(client,request_id):
    # m indexes the file's document archive; the signed plan is the *_20.pdf scan.
    for sequence in (1,2,3,4):
        raw,page_source=client.get(ARCHIVE,dict(appname="cixpa",prgname="ShowPhoto",siteid=121,ec=2,en=request_id,bn=0,m=sequence,arguments="siteid,ec,en,bn,m"))
        if raw.startswith(b"%PDF"):continue
        match=re.search(rb'(https://archive\.gis-net\.co\.il/[^"\']+\.pdf)',raw)
        if not match:continue
        url=match.group(1).decode()
        if f"/{request_id}/" not in url or not url.endswith("_20.pdf"):continue
        pdf,pdf_source=client.get(url)
        if pdf.startswith(b"%PDF"):return pdf,pdf_source,page_source
    raise SourceError(f"No signed plan PDF was exposed for request {request_id}")


def nearby_parcels(client,radius):
    gov=GovMap(client);center=Point(*ANCHOR["itm"])
    rows=gov.parcels(center.buffer(radius),300);out=[]
    for feature in rows:
        props=feature["properties"];geom=shape(feature["geometry"])
        if (props["GUSH_NUM"],props["PARCEL"])==(ANCHOR["gush"],ANCHOR["parcel"]):continue
        if (props.get("LEGAL_AREA") or geom.area)<MIN_PARCEL_AREA:continue
        out.append((round(geom.distance(center),1),feature))
    out.sort(key=lambda x:(x[0],x[1]["properties"]["GUSH_NUM"],x[1]["properties"]["PARCEL"]))
    return out


def collect(target,radius):
    client=PublicClient();archive=BuildingArchive(client)
    (BATCH/"input").mkdir(parents=True,exist_ok=True);(BATCH/"source-records").mkdir(parents=True,exist_ok=True);PERMITS.mkdir(parents=True,exist_ok=True)
    evidence_path=BATCH/"parcel-evidence.json"
    parcel_evidence=json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {}
    cases_path=BATCH/"cases.json"
    cases=json.loads(cases_path.read_text(encoding="utf-8")) if cases_path.exists() else {}
    report=[]
    for distance,feature in nearby_parcels(client,radius):
        if len(cases)>=target:break
        props=feature["properties"];gush,parcel=props["GUSH_NUM"],props["PARCEL"]
        if any(c["gush"]==gush and c["parcel"]==parcel for c in cases.values()):continue
        item={"gush":gush,"parcel":parcel,"distance_m":distance,"state":"skipped"}
        try:
            found=archive.search(gush,parcel)
            item["building_files"]=found["ids"]
            if len(found["ids"])!=1:
                item["reason"]="no single building file for the parcel";report.append(item);log(f"{gush}/{parcel}: {item['reason']} ({found['ids']})");continue
            file_id=found["ids"][0];record=archive.file(file_id);parsed=parse_building_file(record)
            if len(parsed["parcels"])!=1:
                item["reason"]=f"building file spans {len(parsed['parcels'])} parcels";report.append(item);log(f"{gush}/{parcel}: {item['reason']}");continue
            chosen=None
            for request_id in parsed["requests"]:
                raw,page_source=client.get(ARCHIVE,dict(appname="cixpa",prgname="GetBakashaFile",siteid=121,b=request_id,arguments="siteid,b"))
                html=raw.decode("utf-8",errors="replace");page=parse_request_page(html)
                if page["permit"] and page["permit_date"] and page["request_type"]=="בקשה להיתר":
                    chosen=(request_id,page,html,page_source);break
            if not chosen:
                item["reason"]="no issued permit request found";item["requests"]=parsed["requests"];report.append(item);log(f"{gush}/{parcel}: {item['reason']}");continue
            request_id,page,html,page_source=chosen
            pdf,pdf_source,link_source=fetch_plan_pdf(client,request_id)
            name=f"{request_id}-plan.pdf";(BATCH/"input"/name).write_bytes(pdf)
            (PERMITS/f"{request_id}.json").write_text(json.dumps({"id":request_id,"source":page_source,"html":html,"text":text_from_html(html)},ensure_ascii=False,indent=2),encoding="utf-8")
            source_record={"collected_at":utcnow(),"building_file":int(file_id),"gush":gush,"parcel":parcel,"request":request_id,"address":page["address"],
                           "archive_search":found["source"],"building_file_page":record["source"],"request_page":page_source,"download_page":link_source,
                           "pdf":pdf_source,"pdf_sha256":hashlib.sha256(pdf).hexdigest(),"pdf_bytes":len(pdf),
                           "extraction_note":"Public archive metadata only; the request page is stored for table evidence and contains no private data beyond applicant names shown publicly."}
            (BATCH/"source-records"/f"{request_id}.json").write_text(json.dumps(source_record,ensure_ascii=False,indent=2),encoding="utf-8")
            parcel_evidence[f"{gush}-{parcel}"]=[feature];evidence_path.write_text(json.dumps(parcel_evidence,ensure_ascii=False,indent=2),encoding="utf-8")
            cases[str(request_id)]={"address":page["address"],"file":int(file_id),"gush":gush,"parcel":parcel,"permit":page["permit"],"permit_date":page["permit_date"],
                                    "zoning":page["zoning"] or "לא צוין","use":page["use"] or "לא צוין","pdf":name,"units_requested":int(page["units_requested"]) if page["units_requested"] else None,
                                    "distance_from_anchor_m":distance,"other_requests":[x for x in parsed["requests"] if x!=request_id],"plans":parsed["plans"]}
            cases_path.write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding="utf-8")
            item.update({"state":"completed","request":request_id,"address":page["address"],"bytes":len(pdf)});log(f"{gush}/{parcel}: collected file {file_id}, request {request_id}, {page['address']}")
        except Exception as exc:
            item.update({"state":"failed","error":str(exc)});log(f"{gush}/{parcel}: failed: {exc}")
            if "429" in str(exc):log("rate limited; stop and rerun later (responses are cached)");break
        report.append(item)
    summary={"collected_at":utcnow(),"anchor":ANCHOR,"radius_m":radius,"parcels":report,"completed":len(cases)}
    (BATCH/"collection-results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return cases


def build(cases):
    store=Store();store.init();batch_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_root=DATA/"experiments"/"timed-pilot-dossiers"/batch_id;results=[]
    note="תיק שנבנה אוטומטית מתיק הבניין הציבורי, דף הבקשה להיתר ותכנית ההיתר הסרוקה של חלקה סמוכה להשושנים 4. ערכי OCR צורפו כראיה גולמית בלבד ולא הוזנו כשדות; נקודת המבנה נגזרה ממרכז החלקה."
    for request_id,case in cases.items():
        run_id=str(uuid.uuid4());pdf=BATCH/"input"/case["pdf"]
        scan_start=time.perf_counter();ocr=extract_local(pdf,raw_root/str(request_id));scan_seconds=time.perf_counter()-scan_start
        entry_start=time.perf_counter()
        dossier=build_case_dossier(str(request_id),case,BATCH,pipeline_run_id=run_id,selection_note=note)
        dossier["documents"].append({"id":f"{request_id}-ocr","source":{"url":str(ocr["combined_text"]),"retrieved_at":ocr["retrieved_at"]},"pages":len(ocr["tiles"]),"path":ocr["combined_text"],"note":"פלט Tesseract גולמי לאימות אנושי"})
        dossier["gaps"].append("ערכי הדירות, הקומות והשטחים מהתכנית הסרוקה טרם נקראו; פלט ה-OCR מצורף לתיק")
        store.save_dossier(dossier);entry_seconds=time.perf_counter()-entry_start
        store.prune_dossier_versions(dossier["building_id"],keep=1)
        row={"id":run_id,"batch_id":batch_id,"request_id":str(request_id),"building_id":dossier["building_id"],"dossier_id":dossier["id"],"address":case["address"],
             "scan_seconds":round(scan_seconds,3),"data_entry_seconds":round(entry_seconds,3),"total_seconds":round(scan_seconds+entry_seconds,3),
             "ocr_tiles":len(ocr["tiles"]),"ocr_characters":sum(x["characters"] for x in ocr["tiles"]),"raw_output":str((raw_root/str(request_id)).relative_to(ROOT)),
             "created_at":datetime.now(timezone.utc).isoformat(),
             "measurement_scope":"scan includes local PDF rendering, Tesseract OCR and evidence-file writes; data entry includes dossier assembly and SQLite insert; network and operator review are excluded"}
        store.save_pipeline_run(row);results.append(row);log(f"{request_id}: dossier {dossier['id']} ({row['total_seconds']}s)")
    report={"batch_id":batch_id,"runs":results,"totals":{k:round(sum(x[k] for x in results),3) for k in ("scan_seconds","data_entry_seconds","total_seconds")}}
    (BATCH/"timing-results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


def main():
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser();parser.add_argument("--target",type=int,default=5);parser.add_argument("--radius",type=float,default=160)
    parser.add_argument("--skip-collect",action="store_true");parser.add_argument("--skip-build",action="store_true")
    args=parser.parse_args()
    cases=json.loads((BATCH/"cases.json").read_text(encoding="utf-8")) if args.skip_collect else collect(args.target,args.radius)
    log(f"{len(cases)} cases ready")
    if not args.skip_build and cases:print(json.dumps(build(cases),ensure_ascii=False,indent=2))


if __name__=="__main__":main()
