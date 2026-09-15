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

JUMP_M = 2.0


def built_parcels(parcels, buildings, min_area=20.0):
    """איזו חלקה בנויה. כל מבנה שייך לחלקה אחת — זו שמכילה את נקודת הפנים שלו.

    חפיפה בשטח לא עובדת: טביעות הרגל אינן מיושרות לקדסטר, ומבנים גולשים
    כמה מ״ר לתוך חלקת הדרך — שהייתה נחשבת "בנויה" ועוצרת את הקרן.
    """
    from shapely.strtree import STRtree
    tree = STRtree(parcels)
    built = [False] * len(parcels)
    for b in buildings:
        if b.area < min_area:
            continue
        rp = b.representative_point()
        for j in tree.query(rp):
            if parcels[j].contains(rp):
                built[j] = True
                break
    return built


def frontage_runs_v2(i, parcels, ptree, built, samples=240, max_reach=40.0, min_run=8):
    """חזיתות רחוב, כשהקרן נעצרת רק בחלקה בנויה שממול.

    הגרסה הקודמת דילגה על כל חלקה שנוגעת במגרש — גם על השכן. קרן שיצאה מהגבול
    המשותף עם השכן חצתה אותו ונחתה בחלקה שאחריו, ו"הרוחב" היה עומק מגרש השכן:
    שווידלסון 33.0 במקום 10.4, רופין 29.1 במקום 9.9. וזה עקבי לאורך הרחוב, ולכן
    נראה כמו מדידה.

    כאן: דגימה שהחלקה הראשונה שהיא נוגעת בה היא בנויה — פונה לשכן, לא לרחוב.
    אחרת ממשיכים דרך רצועות לא בנויות (מדרכה, חלקת דרך) עד החלקה הבנויה הראשונה.
    """
    g = parcels[i]
    b = g.boundary
    if b.geom_type != "LineString":
        b = max(b.geoms, key=lambda x: x.length)
    L = b.length
    if L <= 0:
        return []
    gb = g.buffer(1.5)
    hits = []
    for s in range(samples):
        d = L * s / samples
        pt = b.interpolate(d); p2 = b.interpolate(min(d + 0.3, L))
        dx, dy = p2.x - pt.x, p2.y - pt.y; m = math.hypot(dx, dy)
        if m == 0: hits.append(None); continue
        nx, ny = dy/m, -dx/m
        if g.contains(Point(pt.x + nx*0.3, pt.y + ny*0.3)): nx, ny = -nx, -ny
        ray = LineString([(pt.x + nx*0.15, pt.y + ny*0.15),
                          (pt.x + nx*max_reach, pt.y + ny*max_reach)])
        seq = sorted((pt.distance(it), j) for j in ptree.query(ray) if j != i
                     for it in [ray.intersection(parcels[j])] if not it.is_empty)
        best = None
        if not (seq and seq[0][0] < 1.0 and built[seq[0][1]]):
            for dist, j in seq:
                if dist < 1.0 or not built[j] or parcels[j].intersects(gb):
                    continue                       # רצועה, או שכן פינתי שנראה באלכסון
                best = dist
                break
        hits.append((pt, nx, ny, best) if best else None)
    # חזית אחת יכולה להחזיק שני רוחבות (מובשוביץ 13: חצי 6 מ׳, חצי 12), ודגימות שברחו
    # יושבות לצד דגימות נכונות. חציון על כולן מטשטש את שני המקרים — לכן קפיצה של מעל
    # JUMP_M פותחת חזית חדשה.
    runs, cur = [], []
    for h in hits + [None]:
        if h and cur and abs(h[3] - statistics.median(x[3] for x in cur[-5:])) > JUMP_M:
            if len(cur) >= min_run: runs.append(cur)
            cur = []
        if h: cur.append(h)
        else:
            if len(cur) >= min_run: runs.append(cur)
            cur = []
    return [dict(width=round(statistics.median(h[3] for h in r), 1),
                 samples=[(h[0].x, h[0].y, h[1], h[2], h[3]) for h in r],
                 pts=[(h[0].x, h[0].y) for h in r],
                 normal=(statistics.mean(h[1] for h in r), statistics.mean(h[2] for h in r)),
                 length=round(len(r)/len(hits) * L, 1))
            for r in runs]


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
