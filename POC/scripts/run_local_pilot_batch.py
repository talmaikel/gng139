"""Run the free OCR pilot for the documents registered in a batch folder."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.openai_pipeline import PipelineError
from app.pilot_batch import run_batch

parser = argparse.ArgumentParser()
parser.add_argument("--batch", type=Path, default=ROOT / "data" / "pilot-batch-01")
args = parser.parse_args()
try:
    report = run_batch(args.batch)
except PipelineError as exc:
    raise SystemExit(f"Pilot not run: {exc}")
print(json.dumps({"completed": report["completed"], "failed": report["failed"], "cost_usd": 0, "report": str(args.batch / "batch-results.json")}, ensure_ascii=False))
