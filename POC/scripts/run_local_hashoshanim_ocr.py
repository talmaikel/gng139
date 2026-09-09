"""Run free, local Hebrew OCR on the Hashoshanim 4 permit drawing."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.local_ocr import extract_local
from app.openai_pipeline import PipelineError

SOURCE = ROOT / "data" / "verification" / "hashoshanim-4" / "1970-plan.pdf"
OUTPUT = ROOT / "data" / "experiments" / "hashoshanim-4-1970-plan-local-ocr"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--psm", type=int, default=11)
    args = parser.parse_args()
    try:
        result = extract_local(SOURCE, OUTPUT, psm=args.psm)
    except PipelineError as exc:
        raise SystemExit(f"Experiment not run: {exc}")
    print(json.dumps({
        "output": str(OUTPUT / "result.json"),
        "tiles": len(result["tiles"]),
        "characters": sum(tile["characters"] for tile in result["tiles"]),
        "cost_usd": result["cost_usd"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
