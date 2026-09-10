"""Finalize Tel Aviv dossiers after the user completes OCR review decisions."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DATA
from app.exports import excel_export, pdf_export
from app.store import Store
from app.tel_aviv import TARGETS, finalize_reviewed_dossier


def main():
    root = DATA / "cities" / "tel-aviv" / "david-hamelech"
    decisions = json.loads((root / "review" / "review-decisions.json").read_text(encoding="utf-8"))
    by_address = {}
    for row in decisions["candidates"]:
        by_address.setdefault(row.get("address") or row.get("house_number"), []).append(row)
    store = Store(); store.init()
    completed = []
    for house, target in TARGETS.items():
        folder = root / str(house)
        pre_review = json.loads((folder / "pre-review-dossier.json").read_text(encoding="utf-8"))
        relevant_ids = {doc["id"] for doc in pre_review["documents"]}
        subset = {"candidates": [row for row in decisions["candidates"] if row["document_id"] in relevant_ids]}
        started = time.perf_counter()
        dossier = finalize_reviewed_dossier(pre_review, subset)
        dossier_path = folder / "dossier.json"
        dossier_path.write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "dossier.pdf").write_bytes(pdf_export(dossier))
        (folder / "dossier.xlsx").write_bytes(excel_export(dossier))
        store.save_dossier(dossier)
        completed.append({"house": house, "dossier_id": dossier["id"], "export_and_store_seconds": round(time.perf_counter() - started, 3)})
    (root / "finalization-results.json").write_text(json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(completed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
