"""Apply human-approved OCR values as a new immutable local dossier snapshot."""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.manual_review import apply_hashoshanim_review
from app.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("decision_file", type=Path)
args = parser.parse_args()
if not args.decision_file.exists():
    raise SystemExit(f"Review file not found: {args.decision_file}")
review_dir = ROOT / "data" / "human-reviews"
review_dir.mkdir(parents=True, exist_ok=True)
preserved = review_dir / "hashoshanim-4-review-decisions.json"
shutil.copy2(args.decision_file, preserved)
store = Store(); store.init()
dossier = apply_hashoshanim_review(preserved, store)
print(json.dumps({"dossier_id": dossier["id"], "accepted": dossier["human_review"]["accepted"], "review_file": str(preserved)}, ensure_ascii=False))
