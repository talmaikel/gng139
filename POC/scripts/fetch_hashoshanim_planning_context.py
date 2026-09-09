"""Fetch the official strategic-renewal map used by Herzliya's Shaked policy."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources import PublicClient


URL = (
    "https://handasa.herzliya.muni.il/wp-content/uploads/2023/09/"
    "תכנית-אסטרטגית-להתחדשות-מרכז-העיר-ינואר-2023-1.pdf"
)


def main() -> None:
    body, meta = PublicClient().get(URL)
    target = Path("data/verification/hashoshanim-4/strategic-renewal-2023.pdf")
    target.write_bytes(body)
    target.with_suffix(".source.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"path": str(target), "bytes": len(body), "source": meta}))


if __name__ == "__main__":
    main()
