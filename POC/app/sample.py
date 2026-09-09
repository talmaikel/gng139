"""Import observed public records, never generated demonstration properties."""
import json
from .config import DATA
from .collector import make_dossier

def import_sample(store):
    base=DATA/'verification'
    required=['sample_audit.json','sample_buildings.json','sample_parcels.json']
    if not all((base/name).exists() for name in required):return []
    audit=json.loads((base/'sample_audit.json').read_text(encoding='utf8'))
    buildings={b['id']:b for b in json.loads((base/'sample_buildings.json').read_text(encoding='utf8'))}
    parcels=json.loads((base/'sample_parcels.json').read_text(encoding='utf8'))
    rows=[]
    for a in audit:
        issues=[{'source':'building_archive','message':a['error']}] if a.get('error') else []
        if a.get('archive',{}).get('status') not in ('found',None):issues.append({'source':'building_archive','message':a['archive']['status']})
        d=make_dossier(buildings[a['building_id']],parcels,a.get('files',[]),{},issues)
        store.save_dossier(d);rows.append(store.dossier(d['id']))
    return rows
