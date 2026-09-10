"""OCR and import the two best remaining pilot files while recording net timings."""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from app.config import DATA
from app.local_ocr import extract_local
from app.pilot_dossiers import BASE, CASES, build_pilot_dossier
from app.store import Store


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--requests",nargs="+",default=["19650106","19610028"])
    args=parser.parse_args()
    store=Store();store.init()
    prune=store.prune_dossier_versions("municipal-file:5848",keep=1)
    batch_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_root=DATA/"experiments"/"timed-pilot-dossiers"/batch_id
    results=[]
    for request_id in args.requests:
        case=CASES[str(request_id)];run_id=str(uuid.uuid4());pdf=BASE/"input"/case["pdf"]
        scan_start=time.perf_counter()
        ocr=extract_local(pdf,raw_root/str(request_id))
        scan_seconds=time.perf_counter()-scan_start
        entry_start=time.perf_counter()
        dossier=build_pilot_dossier(str(request_id),pipeline_run_id=run_id)
        store.save_dossier(dossier)
        entry_seconds=time.perf_counter()-entry_start
        row={
            "id":run_id,"batch_id":batch_id,"request_id":str(request_id),"building_id":dossier["building_id"],
            "dossier_id":dossier["id"],"address":case["address"],"scan_seconds":round(scan_seconds,3),
            "data_entry_seconds":round(entry_seconds,3),"total_seconds":round(scan_seconds+entry_seconds,3),
            "ocr_tiles":len(ocr["tiles"]),"ocr_characters":sum(x["characters"] for x in ocr["tiles"]),
            "raw_output":str((raw_root/str(request_id)).relative_to(ROOT)),"created_at":datetime.now(timezone.utc).isoformat(),
            "measurement_scope":"scan includes local PDF rendering, Tesseract OCR and evidence-file writes; data entry includes dossier assembly and SQLite insert; network and operator review are excluded",
        }
        store.save_pipeline_run(row);results.append(row)
    report={"batch_id":batch_id,"prune":prune,"runs":results,"totals":{
        "scan_seconds":round(sum(x["scan_seconds"] for x in results),3),
        "data_entry_seconds":round(sum(x["data_entry_seconds"] for x in results),3),
        "total_seconds":round(sum(x["total_seconds"] for x in results),3),
    }}
    path=BASE/"timing-results.json";path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
