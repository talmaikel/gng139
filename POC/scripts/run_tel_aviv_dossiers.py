"""Collect, OCR and pause for human review of three Tel Aviv building files."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import DATA
from app.tel_aviv import TARGETS, TelAvivArchiveCollector, TimingReport, build_pre_review_dossier, process_ocr, write_review_package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--houses", nargs="+", type=int, default=[23, 25, 27], choices=sorted(TARGETS))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    root = DATA / "cities" / "tel-aviv" / "david-hamelech"
    root.mkdir(parents=True, exist_ok=True)
    collector = TelAvivArchiveCollector(headless=not args.headed)
    dossiers, reports, timings = [], [], []
    run_started = datetime.now(timezone.utc).isoformat()
    for house in args.houses:
        output = root / str(house)
        timing = TimingReport(TARGETS[house]["address"])
        manifest = collector.collect(house, output, timing)
        report = process_ocr(manifest, output, timing)
        with timing.stage("dossier_assembly"):
            dossier = build_pre_review_dossier(manifest, report)
            (output / "pre-review-dossier.json").write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "timing.json").write_text(json.dumps({"address": timing.address, "stages": timing.stages, "total_seconds": timing.total()}, ensure_ascii=False, indent=2), encoding="utf-8")
        dossiers.append(dossier); reports.append(report); timings.append(timing)
    review_html, decisions = write_review_package(dossiers, reports, root)
    summary = {
        "state": "waiting_for_human_review", "run_started_at": run_started,
        "run_finished_at": datetime.now(timezone.utc).isoformat(),
        "addresses": [{"address": t.address, "total_seconds": t.total(), "stages": t.stages} for t in timings],
        "herzliya_comparison": {"scope": "two saved dossiers; render plus OCR and SQLite assembly; network and human review excluded", "render_and_ocr_seconds": 65.116, "dossier_assembly_seconds": 0.154, "total_seconds": 65.27},
        "review_html": str(review_html), "review_decisions": str(decisions), "api_cost_usd": 0,
    }
    (root / "timing-comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
