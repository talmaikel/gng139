"""Collect three bounded, public Herzliya archive documents for the Neve Israel pilot."""
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.sources import ARCHIVE, BuildingArchive, PublicClient, SourceError, text_from_html, utcnow

BATCH = ROOT / "data" / "pilot-batch-01"
# Selected from three streets identified as Neve Israel. The archive itself confirms the address.
TARGETS = [
    {"building_file": 1652, "gush": 6424, "parcel": 83, "request": 19610028},
    {"building_file": 4461, "gush": 6538, "parcel": 206, "request": 19650106},
    {"building_file": 2772, "gush": 6546, "parcel": 271, "request": 19440048},
]


def address_from_html(raw: str):
    found = re.search(r'top-navbar-info-desc[^>]*>כתובת:</div>\s*<div[^>]*>([^<]+)', raw)
    return found.group(1).strip() if found else None


def download_link(client, request_id: int):
    raw, source = client.get(ARCHIVE, dict(
        appname="cixpa", prgname="ShowPhoto", siteid=121, ec=2, en=request_id, bn=0, m=1,
        arguments="siteid,ec,en,bn,m",
    ))
    match = re.search(r'href="(https://archive\.gis-net\.co\.il/[^"]+\.pdf)"', raw.decode("utf-8", errors="replace"))
    if not match:
        raise SourceError(f"No public PDF link was returned for request {request_id}")
    return match.group(1), source


def main():
    client = PublicClient(); archive = BuildingArchive(client)
    input_dir = BATCH / "input"; metadata_dir = BATCH / "source-records"
    input_dir.mkdir(parents=True, exist_ok=True); metadata_dir.mkdir(parents=True, exist_ok=True)
    rows, report = [], []
    for target in TARGETS:
        request_id = target["request"]
        item = {**target, "state": "failed"}
        try:
            found = archive.search(target["gush"], target["parcel"])
            if str(target["building_file"]) not in found["ids"]:
                raise SourceError("Selected building file is no longer returned for its cadastral parcel")
            raw, page_source = client.get(ARCHIVE, dict(appname="cixpa", prgname="GetBakashaFile", siteid=121, b=request_id, arguments="siteid,b"))
            html = raw.decode("utf-8", errors="replace")
            address = address_from_html(html)
            if not address:
                raise SourceError("Municipal request page did not expose an address")
            pdf_url, link_source = download_link(client, request_id)
            pdf, pdf_source = client.get(pdf_url)
            if not pdf.startswith(b"%PDF"):
                raise SourceError("Municipal archive link did not return a PDF")
            name = f"{request_id}-plan.pdf"
            (input_dir / name).write_bytes(pdf)
            record = {
                "collected_at": utcnow(), "building_file": target["building_file"], "gush": target["gush"], "parcel": target["parcel"],
                "request": request_id, "address": address, "archive_search": found["source"], "request_page": page_source,
                "download_page": link_source, "pdf": pdf_source, "pdf_sha256": hashlib.sha256(pdf).hexdigest(), "pdf_bytes": len(pdf),
                "extraction_note": "Public archive metadata only; full request HTML is not stored because it can contain unnecessary personal data.",
            }
            (metadata_dir / f"{request_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            rows.append({"local_filename": name, "address": address, "municipal_file_number": target["building_file"], "public_source_url": pdf_url, "document_type": "signed permit plan", "notes": f"request {request_id}; gush {target['gush']}; parcel {target['parcel']}"})
            item.update({"state": "completed", "address": address, "pdf": str(input_dir / name), "bytes": len(pdf)})
        except Exception as exc:
            item["error"] = str(exc)
        report.append(item)
    with (BATCH / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["local_filename", "address", "municipal_file_number", "public_source_url", "document_type", "notes"])
        writer.writeheader(); writer.writerows(rows)
    summary = {"collected_at": utcnow(), "area": "נווה ישראל, הרצליה", "documents": report, "completed": sum(x["state"] == "completed" for x in report), "failed": sum(x["state"] == "failed" for x in report)}
    (BATCH / "collection-results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed": summary["completed"], "failed": summary["failed"], "report": str(BATCH / "collection-results.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
