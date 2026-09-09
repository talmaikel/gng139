"""Run repeatable zero-API-cost catalog chunks; use --all only for an unattended run."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.archive_catalog import ArchiveCatalogSync
from app.store import Store

p=argparse.ArgumentParser()
p.add_argument('phase',choices=['discover','hydrate','status'])
p.add_argument('--limit',type=int,default=10,help='Maximum streets/files in this run')
p.add_argument('--all',action='store_true',help='Process the full remaining queue')
p.add_argument('--retry-failed',action='store_true')
a=p.parse_args();store=Store();store.init();sync=ArchiveCatalogSync(store)
if a.phase=='status':result=store.archive_status()
elif a.phase=='discover':
    if a.retry_failed:sync.retry_failed_streets()
    result=sync.discover(None if a.all else a.limit)
else:result=sync.hydrate(None if a.all else a.limit)
print(json.dumps(result,ensure_ascii=False,indent=2))
