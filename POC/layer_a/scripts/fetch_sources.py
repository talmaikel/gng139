"""מוריד את כל המקורות הפתוחים שמהם נבנית שכבה א'.
אפס פניות לארכיון העירוני. ~106MB, כ-20 דקות.

מקורות:
  GovMap WFS            חלקות
  ArcGIS עיריית הרצליה  מבנים (קומות) + נקודות כתובת (דירות)
  iplan XPlan שכבה 4    ייעודי קרקע
  iplan Shimour שכבה 2  שימור
"""
import json, subprocess, sys, time
from _paths import RAW, DATA

BBOX = (181500, 671500, 187500, 678500)       # הרצליה, EPSG:2039
AGOL = "https://services3.arcgis.com/9qGhZGtb39XMVQyR/arcgis/rest/services"
IPLAN = "https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic"

def curl(url, out, data=None):
    cmd = ["curl", "-s", "--max-time", "180", "-A", "Mozilla/5.0", "-o", str(out)]
    if data:
        for k, v in data:
            cmd += ["--data-urlencode", f"{k}={v}"]
        cmd += ["-G", url]
    else:
        cmd += [url]
    subprocess.run(cmd, check=False)
    return out.exists() and out.stat().st_size > 500

def parcels():
    x0, y0, x1, y1 = BBOX
    for i in range(4):
        for j in range(4):
            a, b = x0 + i*1500, y0 + j*1750
            f = RAW / f"par_{i}_{j}.json"
            if f.exists(): continue
            curl("https://open.govmap.gov.il/geoserver/opendata/wfs?service=WFS&version=2.0.0"
                 "&request=GetFeature&typeNames=opendata:Parcels_ITM&outputFormat=application/json"
                 f"&srsName=EPSG:2039&count=6000&bbox={a},{b},{a+1500},{b+1750},EPSG:2039", f)
            print("  parcel tile", i, j, flush=True); time.sleep(1)
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
    print("ייעודי קרקע · XPlan");            iplan_tiles("Xplan", 4, "yeud")
    print("שימור · Shimour");                iplan_tiles("Shimour", 2, "shim")
    print("\nהסתיים. הרץ:  python scripts/build_layer_a.py")
