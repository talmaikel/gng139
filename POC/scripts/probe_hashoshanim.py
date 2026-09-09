"""Collect the public building-file record for Hashoshanim 4."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources import ARCHIVE, BuildingArchive, PublicClient


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    client = PublicClient()
    archive = BuildingArchive(client)
    search = archive.search(6529, 167)
    result = {"search": search, "files": []}
    for building_file_id in search["ids"][:3]:
        result["files"].append(archive.file(building_file_id))
    output = Path("data/verification/hashoshanim-4/archive.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    downloaded = []
    for request_id, sequence, name in [
        (19700069, 1, "1970-plan"),
        (19700069, 2, "1970-permit"),
        (20130304, 3, "2013-plan"),
        (20130304, 4, "2013-permit"),
    ]:
        body, meta = client.get(ARCHIVE, {
            "appname": "cixpa", "prgname": "ShowPhoto", "siteid": 121,
            "ec": 2, "en": request_id, "bn": 0, "m": sequence,
            "arguments": "siteid,ec,en,bn,m",
        })
        if not body.startswith(b"%PDF"):
            match = re.search(rb'window\.location\.href\s*=\s*"([^"]+\.pdf)"', body)
            if match:
                body, meta = client.get(match.group(1).decode("utf-8"))
        suffix = ".pdf" if body.startswith(b"%PDF") else ".bin"
        path = output.parent / f"{name}{suffix}"
        path.write_bytes(body)
        downloaded.append({"path": str(path), "bytes": len(body), "source": meta})
    (output.parent / "document-manifest.json").write_text(
        json.dumps(downloaded, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": search["status"],
        "ids": search["ids"],
        "files": [item["text"][:12000] for item in result["files"]],
        "downloaded": downloaded,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
