"""Download a reproducible Herzliya XPlan snapshot and screen stored parcels."""
import argparse,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.sources import PublicClient,GovMap
from app.store import Store
from app.xplan import XPlanCatalog,XPlanScreen,snapshot_is_fresh

def sync(force=False):
    store=Store();store.init();snapshot=store.latest_xplan_snapshot()
    if force or not snapshot_is_fresh(snapshot):
        boundary=GovMap(PublicClient()).boundary()
        snapshot=XPlanCatalog().download(boundary);store.save_xplan_snapshot(snapshot)
    screener=XPlanScreen(snapshot);counts={}
    for parcel in store.entities('cadastral_parcel'):
        row=screener.screen(parcel);store.save_parcel_screening(row)
        counts[row['category']]=counts.get(row['category'],0)+1
    queue=sum(v for k,v in counts.items() if k in {'primary_candidate','needs_verification'})
    output={'snapshot_id':snapshot['id'],'snapshot_created_at':snapshot['created_at'],
            'layer_counts':{k:len(v) for k,v in snapshot['layers'].items()},
            'stored_parcels_screened':sum(counts.values()),'categories':counts,
            'building_file_pipeline_candidates':queue,
            'estimated_document_pipelines_avoided':sum(counts.values())-queue}
    print(json.dumps(output,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true')
    args=parser.parse_args();sync(args.force)
