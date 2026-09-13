"""שליפת תצלום אוויר עירוני לפי תיבה ב-EPSG:2039.
שירות ציבורי בפורטל ArcGIS Online של עיריית הרצליה, 13 ס"מ לפיקסל.
"""
import json, os, subprocess, math
from PIL import Image
from _paths import RAW

SERVICE = ("https://tiles.arcgis.com/tiles/9qGhZGtb39XMVQyR/arcgis/rest/services/"
           "orto_042022_agol/MapServer")
TILES = RAW / "orto"; TILES.mkdir(exist_ok=True, parents=True)
_INFO = None

def info():
    global _INFO
    if _INFO is None:
        f = TILES / "_service.json"
        if not f.exists():
            subprocess.run(["curl","-s","--max-time","40",f"{SERVICE}?f=json","-o",str(f)],check=False)
        _INFO = json.load(open(f))["tileInfo"]
    return _INFO

def lod_for(res_target=0.1323):
    ti = info()
    return min(ti["lods"], key=lambda l: abs(l["resolution"] - res_target))

def fetch(bbox, res_target=0.1323, pad=5.0):
    """מחזיר (PIL.Image, to_px) — to_px ממיר ITM לפיקסל בתמונה."""
    ti = info(); TS = ti["rows"]
    ox, oy = ti["origin"]["x"], ti["origin"]["y"]
    lod = lod_for(res_target); res, lev = lod["resolution"], lod["level"]
    x0, y0, x1, y1 = bbox
    x0 -= pad; y0 -= pad; x1 += pad; y1 += pad
    span = TS * res
    c0 = int((x0 - ox) // span); c1 = int((x1 - ox) // span)
    r0 = int((oy - y1) // span); r1 = int((oy - y0) // span)
    W = (c1 - c0 + 1) * TS; H = (r1 - r0 + 1) * TS
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            f = TILES / f"{lev}_{r}_{c}.png"
            if not f.exists() or f.stat().st_size < 1500:
                subprocess.run(["curl","-s","--max-time","30",
                                f"{SERVICE}/tile/{lev}/{r}/{c}","-o",str(f)],check=False)
            if f.exists() and f.stat().st_size > 1500:
                try: canvas.paste(Image.open(f).convert("RGB"), ((c-c0)*TS, (r-r0)*TS))
                except Exception: pass
    X0 = ox + c0*span; Y0 = oy - r0*span
    def to_px(x, y): return ((x - X0)/res, (Y0 - y)/res)
    return canvas, to_px, res
