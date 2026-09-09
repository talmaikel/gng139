"""Long-running, resumable citywide catalog job. Safe to stop and rerun."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from app.archive_catalog import ArchiveCatalogSync
from app.store import Store
from app.sources import utcnow

store=Store();store.init();sync=ArchiveCatalogSync(store)
def emit(phase,result):
    print(json.dumps({'at':utcnow(),'phase':phase,**result},ensure_ascii=False),flush=True)

sync.seed_streets()
if store.archive_streets('failed',1):sync.retry_failed_streets()
while store.archive_streets('pending',1):
    result=sync.discover(10);emit('discover',result)
    if result['processed']==0:break
    if result['failed'] and result['completed']<result['processed']:
        failed=store.archive_streets('failed')
        if any('429' in (x.get('error') or '') for x in failed):
            emit('rate_limit_pause',{'seconds':900,'failed_streets':len(failed)});time.sleep(900);sync.retry_failed_streets();continue
        break

if not store.archive_streets('pending',1) and not store.archive_streets('failed',1):
    store.retry_failed_archive_files()
    while store.pending_archive_files(1):
        result=sync.hydrate(10);emit('hydrate',result)
        if result['processed']==0:break
        if result['failed'] and result['completed']<result['processed']:
            failed=store.pending_archive_files()
            if any('429' in (x['payload'].get('last_error') or '') for x in failed):
                emit('rate_limit_pause',{'seconds':900,'failed_files':result['failed']});time.sleep(900);store.retry_failed_archive_files();continue
            break

emit('finished',store.archive_status())
