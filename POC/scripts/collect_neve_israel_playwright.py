"""Reproducible zero-API-cost Playwright collection for the three-building pilot."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.browser_scraper import PlaywrightArchive
from app.sources import SourceError

REQUESTS = [19610028, 19650106, 19440048]
OUTPUT = ROOT / "data" / "pilot-batch-01" / "playwright"

parser = argparse.ArgumentParser()
parser.add_argument("--headed", action="store_true", help="Show Edge while collecting")
args = parser.parse_args()
collector = PlaywrightArchive(headless=not args.headed)
results = []
for request_id in REQUESTS:
    try:
        results.append({"state": "completed", **collector.collect_request(request_id, OUTPUT)})
    except SourceError as exc:
        results.append({"state": "failed", "request_id": request_id, "error": str(exc)})
(OUTPUT / "collection-results.json").parent.mkdir(parents=True, exist_ok=True)
(OUTPUT / "collection-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"completed": sum(x["state"] == "completed" for x in results), "failed": sum(x["state"] == "failed" for x in results), "cost_usd": 0, "report": str(OUTPUT / "collection-results.json")}, ensure_ascii=False))
