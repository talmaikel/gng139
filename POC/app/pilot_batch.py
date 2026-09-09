"""Bounded batch runner for the human-reviewed local OCR pilot."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .local_ocr import extract_local
from .openai_pipeline import PipelineError


def run_batch(batch_dir: Path, *, limit: int = 10):
    manifest = batch_dir / "manifest.csv"
    if not manifest.exists():
        raise PipelineError("manifest.csv is missing from the pilot batch folder")
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows = [row for row in rows if row.get("local_filename") and not row["local_filename"].startswith("example-")]
    if not rows:
        raise PipelineError("No pilot documents listed in manifest.csv")
    if len(rows) > limit:
        raise PipelineError(f"Pilot batch has {len(rows)} documents; the limit is {limit}")
    results = []
    for row in rows:
        document = batch_dir / "input" / row["local_filename"]
        item = {"document": row, "state": "failed", "cost_usd": 0}
        if document.suffix.lower() != ".pdf" or not document.exists():
            item["error"] = "PDF missing from input folder"
        else:
            try:
                output = batch_dir / "output" / document.stem
                result = extract_local(document, output)
                item.update({"state": "completed", "ocr_result": str(output / "result.json"), "tiles": len(result["tiles"]), "characters": sum(x["characters"] for x in result["tiles"])})
            except PipelineError as exc:
                item["error"] = str(exc)
        results.append(item)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "provider": "tesseract", "cost_usd": 0, "documents": results, "completed": sum(x["state"] == "completed" for x in results), "failed": sum(x["state"] == "failed" for x in results)}
    (batch_dir / "batch-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
