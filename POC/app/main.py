import asyncio,json,threading,secrets
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI,HTTPException
from fastapi.responses import FileResponse,HTMLResponse,Response
from fastapi.staticfiles import StaticFiles
from shapely.geometry import shape
from .config import ROOT,DATA,SAMPLE_POLYGON,MAX_AREA_M2,MAX_RADIUS_M,MAX_BUILDINGS,MAX_PARCELS,RULE_VERSION
from .store import Store
from .sources import PublicClient,GovMap
from .geo import wgs,validate_polygon,circle_polygon
from .models import SearchRequest,ScenarioRequest
from .collector import Collector
from .rules import economics,usable
from .exports import pdf_export,excel_export

store=Store();pool=ThreadPoolExecutor(max_workers=1);pending=set();lock=threading.Lock()
def submit(jid):
    with lock:
        if jid in pending:return
        pending.add(jid)
    def work():
        try:Collector(store).run(jid)
        finally:
            with lock:pending.discard(jid)
    pool.submit(work)

@asynccontextmanager
async def lifespan(app):
    store.init()
    for job in store.jobs():
        if job['state']=='queued':submit(job['id'])
    yield

app=FastAPI(title='Shaked real-data POC',lifespan=lifespan)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.get('/',response_class=HTMLResponse)
def index():return (ROOT/'static'/'index.html').read_text(encoding='utf8')
@app.get('/investor-demo',response_class=HTMLResponse)
def investor_demo():return (ROOT/'static'/'index.html').read_text(encoding='utf8')
@app.get('/demo',response_class=HTMLResponse)
def demo():
    body=(ROOT/'shaked-poc (3).html').read_text(encoding='utf8')
    return body.replace('<body style="margin:0">','<body style="margin:0"><div style="background:#fff0c2;padding:12px;text-align:center" dir="rtl">הדגמה נפרדת — כל הנכסים והמחירים במסך זה מדומים. <a href="/">חזרה לנתוני אמת</a></div>')
@app.get('/api/config')
def config():return {'sample_polygon':SAMPLE_POLYGON,'sample_center':{'lat':32.163,'lon':34.8395},'max_area_m2':MAX_AREA_M2,'max_radius_m':MAX_RADIUS_M,'max_buildings':MAX_BUILDINGS,'max_parcels':MAX_PARCELS,'rule_version':RULE_VERSION,'database':'postgresql-postgis' if store.pg else 'sqlite-local','payments':'simulated','company':'pilot','freshness':'pilot-configurable'}
@app.get('/api/health')
def health():return {'status':'ok','database':'postgresql-postgis' if store.pg else 'sqlite-local'}
@app.get('/api/boundary')
def boundary():
    try:
        f=GovMap(PublicClient()).boundary()
        return {'type':'Feature','geometry':wgs(shape(f['geometry'])),'properties':{'name':'הרצליה','source':f['_source']}}
    except Exception as exc:raise HTTPException(503,str(exc))
@app.get('/api/investor-boundary')
def investor_boundary():
    feature=json.loads((DATA/'verification'/'boundary_verified.json').read_text(encoding='utf8'))
    return {'type':'Feature','geometry':wgs(shape(feature['geometry'])),'properties':{'name':'הרצליה','source':'preserved-official-snapshot'}}
@app.get('/api/sources')
def sources():
    p=ROOT/'docs'/'source-matrix.json'
    return json.loads(p.read_text(encoding='utf8')) if p.exists() else []
@app.get('/api/searches')
def searches():return store.jobs()
@app.get('/api/archive-sync')
def archive_sync():return store.archive_status()
@app.post('/api/searches',status_code=202)
def create_search(request:SearchRequest):
    # Geometry preflight does not consume a package. Source outage is not a bad polygon.
    try:b=GovMap(PublicClient()).boundary()
    except Exception as exc:raise HTTPException(503,'Boundary source unavailable: '+str(exc))
    try:
        if request.center:
            circle_polygon(request.center.model_dump(),request.radius_m,shape(b['geometry']),MAX_RADIUS_M,MAX_AREA_M2)
        else:
            validate_polygon(request.polygon,shape(b['geometry']),MAX_AREA_M2)
    except Exception as exc:raise HTTPException(422,str(exc))
    if store.balance()['remaining']==0:raise HTTPException(409,'יש לפתוח חבילת הדגמה חדשה')
    payload=request.model_dump()
    if payload.get('selection_seed') is None:payload['selection_seed']=secrets.randbits(63)
    jid=store.create_job(payload);submit(jid);return {'id':jid}
@app.get('/api/searches/{jid}')
def search(jid:str):
    job=store.job(jid)
    if not job:raise HTTPException(404,'Search not found')
    return job
@app.post('/api/searches/{jid}/retry')
def retry(jid:str):
    job=store.job(jid)
    if not job:raise HTTPException(404,'Search not found')
    if job['state']=='failed':
        store.update(jid,'queued',job['progress'],job['result']);submit(jid);return {'id':jid}
    if job['state']=='completed':
        # A new snapshot can retry source gaps without modifying previous dossiers.
        new_id=store.create_job(job['request']);submit(new_id);return {'id':new_id}
    return {'id':jid}
@app.get('/api/package')
def package():return store.balance()
@app.post('/api/package')
def new_package():store.new_package();return store.balance()
@app.get('/api/dossiers')
def dossiers():return store.dossiers()
@app.post('/api/pilot-sample')
def pilot_sample():
    from .sample import import_sample
    return import_sample(store)
@app.post('/api/hashoshanim-sample')
def hashoshanim_sample():
    from .hashoshanim import import_hashoshanim
    try:return import_hashoshanim(store)
    except (FileNotFoundError,KeyError,ValueError) as exc:
        raise HTTPException(503,'ראיות הניסוי של השושנים 4 אינן שלמות: '+str(exc))
def get_dossier(did):
    d=store.dossier(did)
    if not d:raise HTTPException(404,'Dossier not found')
    return d
@app.get('/api/dossiers/{did}')
def dossier(did:str):return get_dossier(did)
@app.post('/api/dossiers/{did}/scenarios')
def scenario(did:str,request:ScenarioRequest):
    d=get_dossier(did)
    if not usable(d['fields'].get('planning_basis')):raise HTTPException(409,'אין בסיס תכנוני מבוסס; לא ניתן לחשב רווח לתיק זה')
    a=request.model_dump();payload={'assumptions':a,'result':economics(a),'version':'user-scenario-1'}
    return {'id':store.scenario(did,payload),**payload}
@app.get('/api/dossiers/{did}/export/{kind}')
def export(did:str,kind:str):
    d=get_dossier(did)
    if kind=='pdf':return Response(pdf_export(d),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="shaked-{did}.pdf"'})
    if kind=='xlsx':return Response(excel_export(d),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="shaked-{did}.xlsx"'})
    raise HTTPException(404,'Unknown export format')
