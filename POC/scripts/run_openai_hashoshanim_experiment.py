"""Run the first bounded real OpenAI extraction experiment for Hashoshanim 4."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.openai_pipeline import extract, PipelineError


SOURCE = ROOT / "data" / "verification" / "hashoshanim-4" / "1970-plan.pdf"
OUTPUT = ROOT / "data" / "experiments" / "hashoshanim-4-1970-plan"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--model", default="gpt-5.6-luna")
    args = parser.parse_args()
    try:
        result = extract(SOURCE, OUTPUT, model=args.model, max_usd=args.max_usd)
    except PipelineError as exc:
        raise SystemExit(f"Experiment not run: {exc}")
    print(json.dumps({
        "output": str(OUTPUT / "result.json"),
        "tiles": len(result["tiles"]),
        "usage": result["usage"],
        "estimated_cost_usd": result["estimated_cost_usd"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
