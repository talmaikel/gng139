"""Build the no-auto-acceptance human review packet for Hashoshanim 4 OCR."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.manual_review import build_review_packet

result = build_review_packet(
    ROOT / "data" / "experiments" / "hashoshanim-4-1970-plan-local-ocr",
    ROOT / "test-output",
)
print(json.dumps({key: str(value) if isinstance(value, Path) else value for key, value in result.items()}, ensure_ascii=False))
