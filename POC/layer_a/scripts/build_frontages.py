"""בונה את רוחב הרחוב הקובע לכל מועמד.

הסקריפט המקורי לא נשמר בריפו — נשארו רק frontage.py ו-street_frontage.py.

  python scripts/build_frontages.py            # שחזור: raw/frontages_rebuilt.json, מושווה ל-data/frontages.json
  python scripts/build_frontages.py --v2       # data/frontages_v2.json — הקרן נעצרת רק בחלקה בנויה

השחזור הוא השער: הוא נותן את 667 הרוחבות הקיימים בדיוק, ולכן כל הבדל ב-v2 הוא
תוצאה של שינוי האלגוריתם ולא של הנתונים.
"""
import glob, json, math, statistics, sys
from collections import Counter
from pyproj import Transformer
from shapely.geometry import shape, LineString
from shapely.strtree import STRtree
from _paths import RAW, DATA
from frontage import frontage_runs, frontage_runs_v2, built_parcels
from street_frontage import governing_width, narrow_frontages, qualifying

MIN_COMPACTNESS = 0.22     # מתחת לזה — רצועת דרך או מדרכה, לא מגרש (street_widths.py)
MIN_PLOT_AREA = 120


def plots(parcels):
    geoms = []
    for ft in parcels.values():
        try:
            g = shape(ft["geometry"])
        except Exception:
            continue
        if not g.is_valid or g.area <= 0 or g.length <= 0:
            continue
        if 4 * math.pi * g.area / (g.length ** 2) >= MIN_COMPACTNESS and g.area >= MIN_PLOT_AREA:
            geoms.append(g)
    return geoms


def osm_streets():
    to_itm = Transformer.from_crs(4326, 2039, always_xy=True)
    lines, tags, names = [], [], []
    for w in json.load(open(RAW / "osm_highways.json", encoding="utf-8"))["elements"]:
        pts = [to_itm.transform(p["lon"], p["lat"]) for p in w.get("geometry", [])]
        if len(pts) < 2:
            continue
        lines.append(LineString(pts))
        tags.append(w["tags"].get("highway"))
        names.append(w["tags"].get("name"))
    return lines, tags, names


def build(keys):
    parcels = json.load(open(RAW / "parcels.json", encoding="utf-8"))
    P = plots(parcels)
    ptree = STRtree(P)
    streets, tags, names = osm_streets()
    stree = STRtree(streets)
    out, missing = {}, 0
    for i, key in enumerate(keys):
        ft = parcels.get(key)
        if ft is None:
            missing += 1
            continue
        g = shape(ft["geometry"])
        runs = frontage_runs(g, P, ptree)
        w, why, has_street = governing_width(runs, stree, streets, tags, names, parcel=g)
        out[key] = dict(key=key, width=w, why=why, has_street=has_street)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(keys)}", flush=True)
    print(f"מגרשים: {len(P):,} · דרכים: {len(streets):,} · חלקות שחסרות בקדסטר: {missing}")
    return out


class V2:
    """מצב משותף ל-v2: כל החלקות (לא רק "מגרשים"), מבנים, ודרכים. נבנה פעם אחת."""

    def __init__(self):
        parcels = json.load(open(RAW / "parcels.json", encoding="utf-8"))
        self.keys = list(parcels)
        self.idx = {k: i for i, k in enumerate(self.keys)}
        self.G = [shape(parcels[k]["geometry"]) for k in self.keys]
        self.gtree = STRtree(self.G)
        buildings = [shape(f["geometry"]) for p in sorted(glob.glob(str(RAW / "bld_*.json")))
                     for f in json.load(open(p, encoding="utf-8"))["features"] if f.get("geometry")]
        self.built = built_parcels(self.G, buildings)
        self.streets, self.tags, self.names = osm_streets()
        self.stree = STRtree(self.streets)

    def runs(self, key):
        return frontage_runs_v2(self.idx[key], self.G, self.gtree, self.built)

    def parcel(self, key):
        runs = self.runs(key)
        s = (self.stree, self.streets, self.tags, self.names)
        w, why, has_street = governing_width(runs, *s, parcel=self.G[self.idx[key]])
        return dict(key=key, width=w, why=why, has_street=has_street,
                    frontages=[dict(width=x[0], tag=x[1], name=x[2]) for x in qualifying(runs, *s)],
                    narrow=[dict(width=x[0], tag=x[1], name=x[2]) for x in narrow_frontages(runs, *s)])


def build_v2(old):
    v = V2()
    out = []
    for i, key in enumerate(old):
        if key not in v.idx:
            continue
        rec = v.parcel(key)
        rec["width_v1"] = old[key]["width"]
        for f in ("apt", "cat", "gross", "lot"):
            rec[f] = old[key].get(f)
        out.append(rec)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(old)}", flush=True)
    json.dump(out, open(DATA / "frontages_v2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    band = lambda w: "none" if w is None else "≤8" if w <= 8 else "8–9" if w < 9 else "9–10" if w <= 10 \
        else "10–12" if w <= 12 else "12–15" if w <= 15 else ">15"
    cat9 = [r for r in out if r["cat"] == "9"]
    print(f"בנויות: {sum(v.built):,}/{len(v.G):,} חלקות")
    print("קטגוריה 9 · v1:", dict(Counter(band(r["width_v1"]) for r in cat9)))
    print("קטגוריה 9 · v2:", dict(Counter(band(r["width"]) for r in cat9)))
    print(f"חזית צרה מ-8 מ׳ (לבדוק אם רחוב): {sum(1 for r in cat9 if r['narrow'])} · "
          f"בלי חזית בכלל: {sum(1 for r in cat9 if r['width'] is None and not r['narrow'])}")


def compare(new, old):
    both = [k for k in old if k in new]
    d = [(k, old[k]["width"], new[k]["width"]) for k in both]
    same_none = sum(1 for _, a, b in d if a is None and b is None)
    only_one = [(k, a, b) for k, a, b in d if (a is None) != (b is None)]
    diffs = [abs(a - b) for _, a, b in d if a is not None and b is not None]
    print(f"\nהשוואה ל-data/frontages.json · {len(both)} חלקות משותפות")
    print(f"  שני הצדדים ללא רוחב: {same_none} · רק אחד מהם: {len(only_one)}")
    if diffs:
        within = lambda t: sum(1 for x in diffs if x <= t)
        print(f"  שניהם מדדו: {len(diffs)} · ±0.1: {within(0.1)} · ±0.5: {within(0.5)} · ±1.0: {within(1.0)} · "
              f"חציון הפרש {statistics.median(diffs):.2f}")
    has = Counter((old[k]["has_street"], new[k]["has_street"]) for k in both)
    print(f"  has_street (ישן, חדש): {dict(has)}")


if __name__ == "__main__":
    old = {r["key"]: r for r in json.load(open(DATA / "frontages.json", encoding="utf-8"))}
    if "--v2" in sys.argv:
        build_v2(old)
    else:
        keys = [a for a in sys.argv[1:] if not a.startswith("--")] or list(old)
        new = build(keys)
        json.dump(list(new.values()), open(RAW / "frontages_rebuilt.json", "w", encoding="utf-8"), ensure_ascii=False)
        compare(new, old)
