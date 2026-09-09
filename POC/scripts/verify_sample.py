"""Collect ten real discovery buildings and preserve archive evidence/gaps."""
import sys, pathlib, json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from app.sources import PublicClient,GovMap,BuildingArchive,public_buildings
from app.config import DATA,SAMPLE_POLYGON
from app.geo import itm,match_parcels
from shapely.geometry import shape

client=PublicClient(); gov=GovMap(client); out=DATA/'verification'; out.mkdir(exist_ok=True)
boundary=gov.boundary(); (out/'boundary_verified.json').write_text(json.dumps(boundary,ensure_ascii=False),encoding='utf8')
buildings=public_buildings(client,SAMPLE_POLYGON,300)
parcels=gov.parcels(itm(SAMPLE_POLYGON),500)
(out/'sample_buildings.json').write_text(json.dumps(buildings,ensure_ascii=False),encoding='utf8')
(out/'sample_parcels.json').write_text(json.dumps(parcels,ensure_ascii=False),encoding='utf8')
print(f'Buildings: {len(buildings)}, parcels: {len(parcels)}',flush=True)
archive=BuildingArchive(client); sample=[]
for building in buildings[:10]:
 matches=match_parcels(shape(building['geometry']),parcels)
 row={'building_id':building['id'],'building_source':building['_source'],'matches':[{'id':p['id'],'overlap':v,'gush':p['properties']['GUSH_NUM'],'parcel':p['properties']['PARCEL']} for v,p in matches]}
 if matches:
  p=matches[0][1]['properties']
  try:
   row['archive']=archive.search(p['GUSH_NUM'],p['PARCEL'])
   row['files']=[archive.file(t) for t in row['archive']['ids'][:3]]
  except Exception as exc: row['error']=str(exc)
 sample.append(row)
 print(json.dumps({k:v for k,v in row.items() if k not in ['files','archive','building_source']},ensure_ascii=False),flush=True)
 (out/'sample_audit.json').write_text(json.dumps(sample,ensure_ascii=False,indent=2),encoding='utf8')
