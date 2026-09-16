"""שם הייעוד של כל חלקה בשכבה א׳ — ל-#95 (סימון ״ייעוד מעורב״ בשער 70% מגורים).

הזריעה שמרה רק ״יש ייעוד מגורים״ (כן/לא): מרכז החלקה בתוך פוליגון XPlan מאושר
שבשמו ״מגורים״. כך ״מגורים ומסחר״ ו״מגורים ב׳״ נראו אותו דבר. הסקריפט שולף את
שכבת ייעודי הקרקע (iplan XPlan, שכבה 4 — ציבורית, 16 אריחים, שנייה בין בקשות)
וכותב לכל אחת מ-700 החלקות את שמות הייעוד המאושרים שמכילים את מרכזה.

    POC/.venv/bin/python POC/layer_a/scripts/build_zoning_names.py [--raw DIR]

פלט: ‏data/zoning_names.json — ‏{"גוש/חלקה": ["מגורים ב", ...]}. אפס פניות לארכיון.
"""
import argparse, json, subprocess, time
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.strtree import STRtree

from _paths import DATA, RAW

BBOX = (181500, 671500, 187500, 678500)       # הרצליה, EPSG:2039 — כמו fetch_sources.py
IPLAN = "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def fetch(raw: Path) -> None:
    x0, y0, _, _ = BBOX
    for i in range(4):
        for j in range(4):
            a, b = x0 + i * 1500, y0 + j * 1750
            out = raw / f"yeud_{i}_{j}.json"
            if out.exists() and out.stat().st_size > 500:
                continue
            subprocess.run(["curl", "-s", "--max-time", "180", "-A", UA, "-o", str(out), "-G",
                            f"{IPLAN}/Xplan/MapServer/4/query",
                            "--data-urlencode", f"geometry={a},{b},{a + 1500},{b + 1750}",
                            "--data-urlencode", "geometryType=esriGeometryEnvelope",
                            "--data-urlencode", "inSR=2039", "--data-urlencode", "outSR=2039",
                            "--data-urlencode", "spatialRel=esriSpatialRelIntersects",
                            "--data-urlencode", "outFields=mavat_name,station_desc,pl_number",
                            "--data-urlencode", "returnGeometry=true", "--data-urlencode", "f=geojson"],
                           check=False)
            ok = out.exists() and out.read_bytes()[:1] == b"{"
            print("  yeud", i, j, "ok" if ok else "נכשל", flush=True)
            time.sleep(1)


def build(raw: Path) -> dict:
    polys, names = [], []
    for f in sorted(raw.glob("yeud_*.json")):
        for ft in json.load(open(f)).get("features", []):
            p = ft.get("properties") or {}
            if "אישור" not in (p.get("station_desc") or ""):
                continue
            try:
                g = shape(ft["geometry"])
            except Exception:
                continue
            if g.is_valid and g.area > 0:
                polys.append(g)
                names.append((p.get("mavat_name") or "").strip())
    tree = STRtree(polys)
    to_itm = Transformer.from_crs("EPSG:4326", "EPSG:2039", always_xy=True)
    parcels = json.load(open(DATA / "parcels_700.geojson.json"))
    out = {}
    for key, item in parcels.items():
        c = shape(item["geometry"]).centroid
        x, y = to_itm.transform(c.x, c.y)
        from shapely.geometry import Point
        pt = Point(x, y)
        found = sorted({names[i] for i in tree.query(pt) if polys[i].contains(pt) and names[i]})
        out[key] = found
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=RAW, help="היכן לשמור את האריחים הגולמיים (לא ב-git)")
    args = ap.parse_args()
    args.raw.mkdir(parents=True, exist_ok=True)
    fetch(args.raw)
    names = build(args.raw)
    json.dump(names, open(DATA / "zoning_names.json", "w"), ensure_ascii=False, indent=0, sort_keys=True)
    import collections
    c = collections.Counter(n for v in names.values() for n in v)
    print(f"  → {sum(1 for v in names.values() if v)} מתוך {len(names)} חלקות עם שם ייעוד")
    for n, k in c.most_common(15):
        print(f"     {k:>4}  {n}")
