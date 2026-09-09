"""Use OpenAI only for the small evidence crops selected after local OCR."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.openai_pipeline import PipelineError, extract_images

BASE = ROOT / "data" / "pilot-batch-01"
TARGETS = {
    "bar-kochba-12": [{"id": "title", "path": BASE / "output" / "19610028-plan" / "tiles" / "p1-r1-c2.jpg"}],
    "harav-kook-10": [
        {"id": "areas", "path": BASE / "output" / "19650106-plan" / "tiles" / "p1-r1-c10.jpg"},
        {"id": "building-table", "path": BASE / "output" / "19650106-plan" / "tiles" / "p1-r1-c11.jpg"},
        {"id": "title", "path": BASE / "output" / "19650106-plan" / "tiles" / "p1-r1-c12.jpg"},
    ],
    "senesh-hanna-10": [
        {"id": "high-resolution-left", "path": BASE / "targeted-ocr" / "19440048-tiles" / "p1-r1-c1.jpg"},
        {"id": "high-resolution-right", "path": BASE / "targeted-ocr" / "19440048-tiles" / "p1-r1-c2.jpg"},
    ],
}

parser = argparse.ArgumentParser()
parser.add_argument("--max-usd-per-document", type=float, default=0.25)
parser.add_argument("--model", default="gpt-5.6-luna")
args = parser.parse_args()
summary = []
for name, images in TARGETS.items():
    try:
        result = extract_images(images, BASE / "vision" / name, document_label=name, model=args.model, max_usd=args.max_usd_per_document)
        summary.append({"document": name, "state": "completed", "estimated_cost_usd": result["estimated_cost_usd"], "output": str(BASE / "vision" / name / "result.json")})
    except PipelineError as exc:
        summary.append({"document": name, "state": "not_run", "reason": str(exc)})
(BASE / "vision" / "summary.json").parent.mkdir(parents=True, exist_ok=True)
(BASE / "vision" / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
