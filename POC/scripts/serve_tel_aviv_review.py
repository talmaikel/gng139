"""Launch the interactive Tel Aviv OCR review server (local-only)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.review_server:app", host="127.0.0.1", port=8091, reload=False)
