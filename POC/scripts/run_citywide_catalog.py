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

MAX_STALLED_ROUNDS=8
TRANSIENT=('429','ConnectError','getaddrinfo','ReadTimeout','ConnectTimeout','RemoteProtocolError','HTTP 50')

def pause_for(errors):
    """429 means back off hard; network drops (sleep/wake, DNS) recover quickly."""
    if any('429' in e for e in errors):return 900
    if any(any(t in e for t in TRANSIENT) for e in errors):return 120
    return None

sync.seed_streets()
if store.archive_streets('failed',1):sync.retry_failed_streets()
stalled=0
while store.archive_streets('pending',1) or store.archive_streets('failed',1):
    result=sync.discover(10);emit('discover',result)
    if result['completed']:stalled=0
    if result['processed'] and result['failed']:
        errors=[x.get('error') or '' for x in store.archive_streets('failed')];seconds=pause_for(errors)
        if seconds is None:emit('stopped',{'reason':'non-transient street failure','errors':errors[:3]});break
        stalled+=0 if result['completed'] else 1
        if stalled>=MAX_STALLED_ROUNDS:emit('stopped',{'reason':f'{stalled} consecutive rounds without progress','errors':errors[:3]});break
        emit('pause',{'seconds':seconds,'failed_streets':len(errors),'stalled_rounds':stalled});time.sleep(seconds);sync.retry_failed_streets();continue
    if result['processed']==0:break

if not store.archive_streets('pending',1) and not store.archive_streets('failed',1):
    store.retry_failed_archive_files();stalled=0
    while store.pending_archive_files(1):
        result=sync.hydrate(10);emit('hydrate',result)
        if result['completed']:stalled=0
        if result['processed'] and result['failed']:
            errors=[x['payload'].get('last_error') or '' for x in store.pending_archive_files() if x['payload'].get('last_error')];seconds=pause_for(errors)
            if seconds is None:emit('stopped',{'reason':'non-transient file failure','errors':errors[:3]});break
            stalled+=0 if result['completed'] else 1
            if stalled>=MAX_STALLED_ROUNDS:emit('stopped',{'reason':f'{stalled} consecutive rounds without progress','errors':errors[:3]});break
            emit('pause',{'seconds':seconds,'failed_files':result['failed'],'stalled_rounds':stalled});time.sleep(seconds);store.retry_failed_archive_files();continue
        if result['processed']==0:break

emit('finished',store.archive_status())
