"""מוריד את כל המקורות הפתוחים שמהם נבנית שכבה א'.
אפס פניות לארכיון העירוני. ~106MB, כ-20 דקות.

מקורות:
  GovMap WFS            חלקות
  ArcGIS עיריית הרצליה  מבנים (קומות) + נקודות כתובת (דירות) + רחובות (היררכיה)
  OpenStreetMap         דרכים (Overpass)
  iplan XPlan שכבה 4    ייעודי קרקע
  iplan Shimour שכבה 2  שימור
"""
import json, subprocess, sys, time
from _paths import RAW, DATA

BBOX = (181500, 671500, 187500, 678500)       # הרצליה, EPSG:2039
AGOL = "https://services3.arcgis.com/9qGhZGtb39XMVQyR/arcgis/rest/services"
IPLAN = "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic"

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

def curl(url, out, data=None, referer=None, post=False, ua=BROWSER_UA, max_time=180):
    cmd = ["curl", "-s", "--max-time", str(max_time), "-A", ua, "-o", str(out)]
    if referer:
        cmd += ["-H", f"Referer: {referer}"]
    if data:
        for k, v in data:
            cmd += ["--data-urlencode", f"{k}={v}"]
        cmd += [url] if post else ["-G", url]
    else:
        cmd += [url]
    subprocess.run(cmd, check=False)
    # שער gov.il מחזיר דף שגיאה HTML עם 200 — גדול מספיק כדי לעבור בדיקת גודל.
    if not out.exists() or out.stat().st_size <= 500 or out.read_bytes()[:1] not in (b"{", b"["):
        out.unlink(missing_ok=True)
        return False
    return True

def parcels():
    x0, y0, x1, y1 = BBOX
    for i in range(4):
        for j in range(4):
            a, b = x0 + i*1500, y0 + j*1750
            f = RAW / f"par_{i}_{j}.json"
            if f.exists(): continue
            curl("https://open.govmap.gov.il/geoserver/opendata/wfs?service=WFS&version=2.0.0"
                 "&request=GetFeature&typeNames=opendata:Parcels_ITM&outputFormat=application/json"
                 f"&srsName=EPSG:2039&count=6000&bbox={a},{b},{a+1500},{b+1750},EPSG:2039", f,
                 referer="https://www.govmap.gov.il/")
            print("  parcel tile", i, j, "ok" if f.exists() else "נכשל", flush=True); time.sleep(1)
    seen = {}
    for f in RAW.glob("par_*.json"):
        for ft in json.load(open(f)).get("features", []):
            p = ft["properties"]; seen[f"{p['GUSH_NUM']}/{p['PARCEL']}"] = ft
    json.dump(seen, open(RAW / "parcels.json", "w"))
    print(f"  → {len(seen):,} חלקות")

def agol_layer(service, layer, prefix, fields, total):
    for off in range(0, total + 2000, 2000):
        f = RAW / f"{prefix}_{off}.json"
        if f.exists(): continue
        curl(f"{AGOL}/{service}/FeatureServer/{layer}/query", f, [
            ("where", "1=1"), ("outFields", fields), ("orderByFields", "OBJECTID"),
            ("resultOffset", off), ("resultRecordCount", 2000),
            ("outSR", "2039"), ("returnGeometry", "true"), ("f", "geojson")])
        print("  ", prefix, off, flush=True); time.sleep(2)

def osm_highways():
    """דרכי OSM — לשיוך חזית לרחוב ולסוג הדרך. לא למדידה: הציר אינו מיושר לקדסטר."""
    f = RAW / "osm_highways.json"
    if f.exists():
        print("  קיים"); return
    s, w, n, e = 32.120, 34.760, 32.210, 34.880     # BBOX ב-WGS84, עם שוליים
    query = f'[out:json][timeout:180];way["highway"]({s},{w},{n},{e});out tags geom;'
    # ‏Overpass דוחה UA של דפדפן (406) ומחזיר 504 כשהוא עמוס — מזדהים, ומנסים שוב.
    for attempt in range(3):
        ok = curl("https://overpass-api.de/api/interpreter", f, [("data", query)], post=True,
                  ua="ShakedEngine/1.0 public-data research", max_time=240)
        if ok: break
        time.sleep(30)
    print(f"  → {len(json.load(open(f))['elements']):,} דרכים" if ok else "  נכשל")

def iplan_tiles(service, layer, prefix):
    x0, y0, _, _ = BBOX
    for i in range(4):
        for j in range(4):
            a, b = x0 + i*1500, y0 + j*1750
            f = RAW / f"{prefix}_{i}_{j}.json"
            if f.exists(): continue
            curl(f"{IPLAN}/{service}/MapServer/{layer}/query", f, [
                ("geometry", f"{a},{b},{a+1500},{b+1750}"),
                ("geometryType", "esriGeometryEnvelope"), ("inSR", "2039"), ("outSR", "2039"),
                ("spatialRel", "esriSpatialRelIntersects"),
                ("outFields", "mavat_name,station_desc,pl_number"),
                ("returnGeometry", "true"), ("f", "geojson")])
            time.sleep(1)
    print(f"  → {prefix} הושלם")

def policy_map():
    """מפת המדיniyut — הר/2323. ההתמרה ב-data/policy_map_affine.npy מכוילת לקובץ הזה בדיוק."""
    f = DATA / "strategic.pdf"
    if f.exists():
        print("  מפת מדיניות: קיימת"); return
    sys.exit("חסר data/strategic.pdf — התכנית האסטרטגית הר/2323.\n"
             "הקובץ מגיע עם הריפו. ההתמרה ב-policy_map_affine.npy מכוילת לעותק הזה בדיוק,\n"
             "ולכן החלפתו בגרסה אחרת תדרוש כיול מחדש.")

if __name__ == "__main__":
    print("מפת המדיניות · הר/2323");         policy_map()
    print("חלקות · GovMap WFS");            parcels()
    print("מבנים · ArcGIS עירוני")
    agol_layer("herzliya_reka_2023", 3, "bld",
               "Num_floors,bldg_type,status,PUB_PRVT,street_nam,BLDG_NUM", 14072)
    print("נקודות כתובת · ArcGIS עירוני")
    agol_layer("%D7%9E%D7%A1%D7%A4%D7%A8%D7%99_%D7%91%D7%AA%D7%99%D7%9D_%D7%97%D7%93%D7%A9", 43, "apt",
               "num_aprt,amudim,num_floors_numtype,street_nam,BLDG_NUM,shimush_t4", 14624)
    print("רחובות עירוניים · היררכיה (rashi)")
    agol_layer("streets_01_2026", 28, "str", "NAME,rashi,layer_name,street_cod", 2959)
    print("דרכים · OpenStreetMap");          osm_highways()
    print("ייעודי קרקע · XPlan");            iplan_tiles("Xplan", 4, "yeud")
    print("שימור · Shimour");                iplan_tiles("Shimour", 2, "shim")
    print("\nהסתיים. הרץ:  python scripts/build_layer_a.py")
