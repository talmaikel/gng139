"""זיהוי חזיתות רחוב: איזה רווח סביב החלקה הוא באמת רחוב, ולא שביל או חצר.

הצורך התגלה במדידה: הגבול הצפוני של הצנחנים 15 גובל בשביל של ~2.4 מ',
והאלגוריתם הקודם החזיר לו 8.0 ו-20.4 מ' — שניהם שגויים. בלי לדעת מה רחוב,
מדידת הרוחב מודדת את הדבר הלא נכון.
"""
import math, statistics
from shapely.geometry import Point, LineString, Polygon

def frontage_runs(g, plots, ptree, samples=240, max_reach=40.0, min_run=8):
    """מחזיר רשימת חזיתות: (רוחב_חציוני, [נקודות_על_הגבול], כיוון_החוצה)."""
    touch = {i for i in ptree.query(g.buffer(1.5)) if plots[i].intersects(g.buffer(1.5))}
    b = g.boundary
    if b.geom_type != "LineString":
        b = max(b.geoms, key=lambda x: x.length)
    L = b.length
    if L <= 0: return []
    hits = []
    for i in range(samples):
        d = L * i / samples
        pt = b.interpolate(d); p2 = b.interpolate(min(d + 0.3, L))
        dx, dy = p2.x - pt.x, p2.y - pt.y; m = math.hypot(dx, dy)
        if m == 0: hits.append(None); continue
        nx, ny = dy/m, -dx/m
        if g.contains(Point(pt.x + nx*0.3, pt.y + ny*0.3)): nx, ny = -nx, -ny
        ray = LineString([(pt.x + nx*0.15, pt.y + ny*0.15),
                          (pt.x + nx*max_reach, pt.y + ny*max_reach)])
        best = None
        for j in ptree.query(ray):
            if j in touch: continue
            it = ray.intersection(plots[j])
            if it.is_empty: continue
            dd = pt.distance(it)
            if best is None or dd < best: best = dd
        hits.append((pt, nx, ny, best) if best and 1.0 < best < max_reach else None)
    runs, cur = [], []
    for h in hits:
        if h: cur.append(h)
        else:
            if len(cur) >= min_run: runs.append(cur)
            cur = []
    if len(cur) >= min_run: runs.append(cur)
    out = []
    for r in runs:
        w = statistics.median([h[3] for h in r])
        out.append(dict(width=round(w, 1),
                        # נורמל פר-נקודה. ממוצע על חזית מעוקלת מצביע לכיוון שגוי
                        # ושולח את קרן הסיווג הצידה במקום לחצות את הרווח.
                        samples=[(h[0].x, h[0].y, h[1], h[2], h[3]) for h in r],
                        pts=[(h[0].x, h[0].y) for h in r],
                        normal=(statistics.mean([h[1] for h in r]),
                                statistics.mean([h[2] for h in r])),
                        length=round(len(r)/len(hits) * g.boundary.length, 1)))
    return out

def strip_polygon(run):
    """מלבן מקורב מעל הרווח — לדגימה מהאורתופוטו."""
    pts = run["pts"]; nx, ny = run["normal"]; w = run["width"]
    inner = [(x + nx*0.4, y + ny*0.4) for x, y in pts]
    outer = [(x + nx*(w - 0.4), y + ny*(w - 0.4)) for x, y in reversed(pts)]
    try:
        p = Polygon(inner + outer)
        return p if p.is_valid and p.area > 4 else p.buffer(0)
    except Exception:
        return None
