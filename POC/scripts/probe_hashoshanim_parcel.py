"""Download the current official cadastral feature for Hashoshanim 4."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources import GovMap, PublicClient
from app.sources import public_buildings
from app.geo import wgs
from shapely.geometry import shape


def main() -> None:
    rows = GovMap(PublicClient()).features(
        "opendata:Parcels_ITM", "GUSH_NUM=6529 AND PARCEL=167", limit=5
    )
    path = Path("data/verification/hashoshanim-4/current-parcel.json")
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    buildings = public_buildings(PublicClient(), wgs(shape(rows[0]["geometry"])), 20)
    (path.parent / "current-buildings.json").write_text(
        json.dumps(buildings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps([
        {"id": row["id"], "properties": row["properties"], "source": row["_source"]}
        for row in rows
    ], ensure_ascii=False))
    print(json.dumps([
        {"id": row["id"], "properties": row["properties"], "source": row["_source"]}
        for row in buildings
    ], ensure_ascii=False))


if __name__ == "__main__":
    main()
