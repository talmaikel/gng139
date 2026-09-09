"""List public Herzliya GIS layers relevant to Shaked eligibility."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources import ArcGIS, PublicClient


def main() -> None:
    client = PublicClient()
    service = ArcGIS(client, "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer")
    data, _ = client.json(service.url(), {"f": "json"})
    for layer in data.get("layers", []):
        print(f"{layer['id']}: {layer['name']}")


if __name__ == "__main__":
    main()
