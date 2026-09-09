"""Read-only public source probes; preserve responses for reproducible verification."""
import json, pathlib, urllib.request, urllib.error, re, datetime, http.cookiejar, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'verification'
OUT.mkdir(parents=True, exist_ok=True)
URLS = {
 'gis_page': 'https://v5.gis-net.co.il/v5/Hertzeliya',
 'gis_map': 'https://v5.gis-net.co.il/V5/Hertzeliya/Data/GetMap',
 'gis_json': 'https://v5.gis-net.co.il/V5/Hertzeliya/Data/GetJson',
 'gis_script': 'https://v5.gis-net.co.il/V5/site/js?v=rtjFVSPjVbm2xQiavT9LjeD7jbXlamoNoTUhnlTMsVI1',
 'wfs_catalog': 'https://open.govmap.gov.il/geoserver/opendata/wfs?service=WFS&request=GetCapabilities',
 'municipality_schema': 'https://open.govmap.gov.il/geoserver/opendata/wfs?service=WFS&version=2.0.0&request=DescribeFeatureType&typeNames=opendata:muni_il&outputFormat=application/json',
 'parcel_schema': 'https://open.govmap.gov.il/geoserver/opendata/wfs?service=WFS&version=2.0.0&request=DescribeFeatureType&typeNames=opendata:Parcels_ITM&outputFormat=application/json',
 'engineering': 'https://handasa.herzliya.muni.il/',
 'municipal_layers': 'https://v5.gis-net.co.il/proxy/proxy.ashx?http://arcgis005/arcgis/rest/services/Herzliya/herzliya_main_date1/MapServer?f=json',
 'planning_layers': 'https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer?f=json',
 'archive': 'https://handasa.herzliya.muni.il/tikbinyan/',
 'renewal': 'https://handasa.herzliya.muni.il/urbanrenewal/',
 'boundary': 'https://open.govmap.gov.il/geoserver/opendata/wfs?service=WFS&version=2.0.0&request=GetFeature&typeNames=opendata:muni_il&outputFormat=application/json&srsName=EPSG:2039&CQL_FILTER=CR_LAMAS%3D%276400%27',
 'direct_layers': 'https://v5.gis-net.co.il/arcgis/rest/services/Herzliya/herzliya_main_date1/MapServer?f=json',
 'archive_routes': 'https://handasi.complot.co.il/handasi2016/Scripts/Complot/building/min/_routes.min.js',
 'archive_globals': 'https://handasi.complot.co.il/handasi2016/Scripts/globals.js',
 'archive_site': 'https://handasi.complot.co.il/handasi2016/Scripts/wp/site.min.js',
 'archive_search': 'https://handasi.complot.co.il/handasi2016/building/building-index.htm',
 'archive_search_js': 'https://handasi.complot.co.il/handasi2016/Scripts/Complot/Building/min/building-index.min.js',
 'public_gis': 'https://v5.gis-net.co.il/v5/Hertzeliya?minisite=public',
 'public_config': 'https://v5.gis-net.co.il/V5/Hertzeliya/Data/GetJson?minisite=public',
 'osm_buildings': 'https://overpass-api.de/api/interpreter?data='+urllib.parse.quote('[out:json][timeout:25];way["building"](32.162,34.838,32.166,34.844);out tags geom;'),
 'policy_pdf': 'https://handasa.herzliya.muni.il/wp-content/uploads/2026/04/'+urllib.parse.quote('מדיניות-בניה-חלופת-שקד-אפריל-2026.pdf'),
}
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
opener.addheaders = [('User-Agent','ShakedPOC/0.1 public-data feasibility'), ('Referer',URLS['gis_page']), ('X-Requested-With','XMLHttpRequest')]
results = []
for name, url in URLS.items():
 if len(sys.argv)>1 and name not in sys.argv[1:]: continue
 try:
  with opener.open(url, timeout=25) as r:
   body=r.read(); (OUT / (name+'.txt')).write_bytes(body)
   result=dict(name=name,url=url,status=r.status,bytes=len(body),retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 except Exception as e: result=dict(name=name,url=url,error=str(e))
 results.append(result); print(json.dumps(result,ensure_ascii=False),flush=True)
old=json.loads((OUT/'probes.json').read_text(encoding='utf-8')) if (OUT/'probes.json').exists() else []
names={r['name'] for r in results}
(OUT/'probes.json').write_text(json.dumps([r for r in old if r['name'] not in names]+results,ensure_ascii=False,indent=2),encoding='utf-8')
