import copy,json,zipfile,io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import httpx,pytest
from shapely.geometry import box,mapping,Polygon
from app.geo import itm,wgs,center_selected,match_parcels,pair_geometry,validate_polygon,circle_polygon
from app.sources import PublicClient,GovMap,ArcGIS,SourceError,utcnow
from app.models import SearchRequest,ScenarioRequest
from app.rules import evaluate,evidence,usable,rank,economics,resolve_evidence
from app.store import Store
from app.collector import make_dossier,randomized_order
from app.documents import archive_tables,collect_pdf
from app.exports import excel_export,pdf_export

def official(value):return evidence(value,{'url':'https://example.org/source','retrieved_at':utcnow()},'official','page 1','test')
def test_coordinate_roundtrip_and_area():
    g=mapping(box(34.84,32.16,34.841,32.161));assert shape_equal(g,wgs(itm(g)))
    assert 9000<itm(g).area<12000
def shape_equal(a,b):
    from shapely.geometry import shape
    return shape(a).hausdorff_distance(shape(b))<1e-7
def test_centroid_boundary_inclusive():
    assert center_selected(box(-1,-1,1,1),box(0,0,10,10))
    assert not center_selected(box(-3,-3,-1,-1),box(0,0,10,10))
def test_polygon_city_area_and_self_intersection():
    g=mapping(box(34.84,32.16,34.841,32.161));p=itm(g)
    assert validate_polygon(g,p.buffer(10),20000).is_valid
    with pytest.raises(ValueError):validate_polygon(g,p.buffer(10),100)
    with pytest.raises(ValueError):validate_polygon(g,p.buffer(-1),20000)
    with pytest.raises(ValueError):validate_polygon(mapping(Polygon([(0,0),(1,1),(0,1),(1,0),(0,0)])),p,20000)
def test_circle_is_metric_and_must_fit_city():
    boundary=itm(mapping(box(34.83,32.15,34.86,32.18)))
    circle=circle_polygon({'lat':32.165,'lon':34.845},100,boundary,250,250000)
    assert 31000<circle.area<31500
    with pytest.raises(ValueError,match='250'):circle_polygon({'lat':32.165,'lon':34.845},251,boundary,250,250000)
def test_parcel_overlap_not_nearest_neighbor():
    a={'id':'a','geometry':mapping(box(0,0,5,10))};b={'id':'b','geometry':mapping(box(5,0,10,10))}
    matches=match_parcels(box(0,0,10,10),[b,a]);assert [x[1]['id'] for x in matches]==['a','b'];assert matches[0][0]==.5
def test_pair_requires_shared_boundary_and_evidence():
    assert pair_geometry(box(0,0,1,1),box(1,0,2,1),False) is None
    assert pair_geometry(box(0,0,1,1),box(1,0,2,1),True).area==2
    assert pair_geometry(box(0,0,1,1),box(1,1,2,2),True) is None
def test_wfs_pages_and_truncation(tmp_path):
    def response(request):
        start=int(request.url.params['startIndex']);batch=[{'id':str(i),'geometry':None,'properties':{}} for i in range(start,min(start+2,5))]
        return httpx.Response(200,json={'type':'FeatureCollection','numberMatched':5,'features':batch})
    gov=GovMap(PublicClient(tmp_path,transport=httpx.MockTransport(response)))
    assert len(gov.features('layer','1=1',limit=5,page_size=2))==5
    with pytest.raises(SourceError):gov.features('layer','1=1',limit=4,page_size=2)
def test_repeated_pages_rejected(tmp_path):
    client=PublicClient(tmp_path,transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'type':'FeatureCollection','numberMatched':5,'features':[{'id':'x'}]})))
    with pytest.raises(SourceError,match='repeated'):GovMap(client).features('layer','1=1',10,1)
def test_html_200_is_not_success(tmp_path):
    c=PublicClient(tmp_path,transport=httpx.MockTransport(lambda r:httpx.Response(200,text='<html>404</html>')))
    with pytest.raises(SourceError,match='Expected JSON'):c.json('https://example.org')
def test_cache_retains_original_retrieval_time(tmp_path):
    calls=[]
    def response(r):calls.append(r);return httpx.Response(200,json={'ok':True})
    c=PublicClient(tmp_path,transport=httpx.MockTransport(response));_,first=c.json('https://example.org');_,second=c.json('https://example.org')
    assert first==second and len(calls)==1
def test_proxy_target_query_separator(tmp_path):
    calls=[]
    def response(r):calls.append(str(r.url));return httpx.Response(200,json={'layers':[]})
    a=ArcGIS(PublicClient(tmp_path,transport=httpx.MockTransport(response)),'http://arcgis005/arcgis/rest/services/a/MapServer')
    with pytest.raises(SourceError):a.discover('buildings')
    assert '/MapServer?f=json' in calls[0]
def test_rules_unknown_and_conditional_permit():
    assert all(c['status']=='unknown' for c in evaluate({},{}))
    for date,status in [('1979-12-31','passed'),('1980-01-01','unknown'),('1984-12-31','unknown'),('1985-01-01','failed')]:
        result=evaluate({'permit_date':official(date)},{});assert next(c for c in result if c['id']=='permit_date')['status']==status
    result=evaluate({'permit_date':official('1982-01-01'),'engineer_opinion':official(True)},{});assert next(c for c in result if c['id']=='permit_date')['status']=='passed'
def test_missing_conflicting_community_and_stale_never_pass():
    for certainty in ['missing','conflict','community']:
        f=official(5);f['certainty']=certainty;assert not usable(f)
    f=official(5);f['source']['retrieved_at']=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat();assert not usable(f)
    result=evaluate({'units':evidence(None)}, {'max_units':20});assert next(c for c in result if c['id']=='filter_units')['status']=='unknown'
def test_lexicographic_missing_last_and_stable_tie():
    rows=[{'id':i,'fields':{'parcel_area':official(v) if v else evidence(None)}} for i,v in [('b',10),('c',None),('a',10),('d',20)]]
    assert [d['id'] for d in rank(rows,[{'field':'parcel_area','direction':'desc'}])]==['d','a','b','c']
    assert [d['id'] for d in rank(rows,[{'field':'parcel_area','direction':'asc'}])]==['a','b','d','c']
def test_random_candidate_order_is_reproducible():
    rows=[{'id':str(i)} for i in range(8)]
    assert randomized_order(rows,139)==randomized_order(list(reversed(rows)),139)
    assert randomized_order(rows,139)!=sorted(rows,key=lambda x:x['id'])

def test_economics_and_validation():
    a={'sale_area':100,'construction_area':150,'sale_price':10,'build_cost':2,'tenant_rent':5,'rent_months':10,'consultants':10,'finance':20,'levies_taxes':30,'parking':40,'reserve':50,'other_costs':0,'tax_basis':'all-inclusive','assumptions_note':'Explicit test assumptions only'}
    validated=ScenarioRequest(**a).model_dump();r=economics(validated);assert r['revenue']==1000 and r['costs']==500 and r['profit']==500 and r['profit_on_cost']==1
    assert r['sensitivity'][4]['profit']==r['profit']
    with pytest.raises(ValueError):ScenarioRequest(**dict(a,sale_price=float('nan')))
    with pytest.raises(ValueError):SearchRequest(polygon={},preferences=[{'field':'units'},{'field':'units'}])

@pytest.fixture
def store(tmp_path):
    s=Store(url='',path=tmp_path/'db.sqlite');s.init();return s
def ready(i,keys=None):return {'id':str(i),'status':'ready','gaps':[],'scenario':{'result':{}},'entity_keys':keys or [str(i)]}
def test_entitlement_atomic_dedup_and_pairs(store):
    rows=[ready(i) for i in range(10)]
    for d in rows:store.save_dossier(d)
    with ThreadPoolExecutor(max_workers=5) as p:list(p.map(lambda _:store.deliver(rows),range(5)))
    assert store.balance()['remaining']==0;assert len(store.balance()['delivered'])==3
    store.new_package();assert store.deliver(rows[:3])==[]
    pair=ready('pair',['0','new']);store.save_dossier(pair);assert store.deliver([pair])==[]
def test_incomplete_never_consumes_and_snapshot_immutable(store):
    d=ready('x');d['gaps']=['missing apartments'];store.save_dossier(d);assert store.deliver([d])==[];assert store.balance()['remaining']==3
    replacement=copy.deepcopy(d);replacement['gaps']=[];store.save_dossier(replacement);assert store.dossier('x')['gaps'];assert store.deliver([replacement])==[]
def test_job_recovery_preserves_checkpoint(store):
    jid=store.create_job({'polygon':{}});store.update(jid,'running',40,{'candidates':[{'id':'x'}]});store.init();job=store.job(jid)
    assert job['state']=='queued' and job['progress']==40 and job['result']['candidates']==[{'id':'x'}]
def test_archive_table_extraction():
    rows=archive_tables('<table><tr><th>מספר בקשה</th><th>שם המבקש</th></tr><tr><td>123</td><td>private name</td></tr></table>')
    assert rows==[{'headers':['מספר בקשה'],'rows':[['123']]}]
    rows=archive_tables('<table><tr><th>סוג בעל עניין</th><th>שם בעל עניין</th><th>טלפון</th></tr><tr><td>מבקש</td><td>private name</td><td>050</td></tr></table>')
    assert rows==[{'headers':['סוג בעל עניין'],'rows':[['מבקש']]}]
def test_conflicting_evidence_preserved():
    f=resolve_evidence([official(8),official(12)])
    assert f['certainty']=='conflict' and not usable(f)
    assert [o['value'] for o in f['observations']]==[8,12]
def test_scanned_pdf_explicit_ocr_gap(tmp_path,monkeypatch):
    import pymupdf
    d=pymupdf.open();d.new_page();raw=d.tobytes();d.close()
    c=PublicClient(tmp_path/'cache',transport=httpx.MockTransport(lambda r:httpx.Response(200,content=raw)))
    def fail(*args,**kw):raise RuntimeError('No OCR language data')
    monkeypatch.setattr(pymupdf.Page,'get_textpage_ocr',fail)
    import app.documents as documents
    monkeypatch.setattr(documents,'DATA',tmp_path)
    result=collect_pdf(c,'https://handasa.herzliya.muni.il/test.pdf');assert result['pages'][0]['method']=='ocr_unavailable';assert not result['critical_facts_auto_verified']

def test_real_sample_and_exports(store,tmp_path):
    from app.sample import import_sample
    rows=import_sample(store)
    if not rows:pytest.skip('Real source audit not present')
    assert len(rows)==10;assert all(d['status']!='ready' for d in rows);assert store.balance()['remaining']==3
    d=rows[0];pdf=pdf_export(d);assert pdf.startswith(b'%PDF');(tmp_path/'dossier.pdf').write_bytes(pdf)
    xlsx=excel_export(d)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
        xml=z.read('xl/worksheets/sheet2.xml').decode();assert 'COUNT(B2:B13)' in xml and 'B3*B5+B6*B7+SUM(B8:B13)' in xml

def test_hashoshanim_calculation_and_source_match():
    from app.hashoshanim import build_hashoshanim_dossier
    d=build_hashoshanim_dossier()
    assert d['eligibility']['passed_count']==6
    assert d['rights_analysis']['base_formula']=='3 × 187.97 + 14.68'
    assert d['rights_analysis']['maximum_total_above_ground_m2']==2314.36
    assert d['rights_analysis']['indicative_whole_unit_range']==[17,19]
    assert d['fields']['strengthened']['value'] is False
    assert d['documents'][0]['source']['sha256']=='78b2f6d26b39326ec3dab3349c36a013b92411b3fe85e244c57c46c497223f40'

def test_openai_pipeline_preflights_budget_and_preserves_evidence(tmp_path,monkeypatch):
    import pymupdf
    from app.openai_pipeline import extract,PipelineError
    pdf=tmp_path/'permit.pdf'; doc=pymupdf.open();doc.new_page().insert_text((72,72),'היתר 99');doc.save(pdf);doc.close()
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    calls=[]
    def responder(request):
        calls.append(request)
        if request.url.path.endswith('input_tokens'):
            return httpx.Response(200,json={'input_tokens':100})
        body={'id':'resp-test','usage':{'input_tokens':100,'output_tokens':50},'output':[{'content':[{'type':'output_text','text':json.dumps({'fields':{k:{'value':None,'page':None,'tile':None,'quote':None,'confidence':0} for k in ['permit_number','permit_date','units','residential_floors','pilotis_floors','main_residential_area_m2','stair_area_m2','pilotis_area_m2','shelter_area_m2','original_total_area_m2']},'notes':'test'},ensure_ascii=False)}]}]}
        return httpx.Response(200,json=body)
    result=extract(pdf,tmp_path/'output',transport=httpx.MockTransport(responder))
    assert len(calls)==2 and result['usage']['input_tokens']==100
    assert result['estimated_cost_usd']==0.00008
    assert (tmp_path/'output'/'result.json').exists()
    with pytest.raises(PipelineError,match='ceiling'):
        extract(pdf,tmp_path/'too-expensive',max_usd=.0001,transport=httpx.MockTransport(responder))

def test_local_ocr_retains_raw_text_by_tile(tmp_path,monkeypatch):
    import pymupdf
    import app.local_ocr as local_ocr
    pdf=tmp_path/'permit.pdf'; doc=pymupdf.open();doc.new_page().insert_text((72,72),'permit');doc.save(pdf);doc.close()
    monkeypatch.setattr(local_ocr,'_tesseract_command',lambda:'tesseract')
    class Done:
        returncode=0;stderr=''
        def __init__(self,stdout):self.stdout=stdout
    def run(args,**kwargs):
        return Done('List of available languages in x:' + chr(10) + 'heb' + chr(10) + 'eng') if '--list-langs' in args else Done('\u05d4\u05d9\u05ea\u05e8 99')
    monkeypatch.setattr(local_ocr.subprocess,'run',run)
    result=local_ocr.extract_local(pdf,tmp_path/'output')
    assert result['cost_usd']==0 and result['tiles'][0]['characters']==7
    assert (tmp_path/'output'/'ocr.txt').read_text(encoding='utf8').endswith('\u05d4\u05d9\u05ea\u05e8 99')

def test_human_review_packet_never_auto_accepts(tmp_path):
    from app.manual_review import build_review_packet
    result=build_review_packet(tmp_path/'ocr',tmp_path/'review')
    packet=json.loads(result['json'].read_text(encoding='utf8'))
    assert result['candidates']==12 and packet['accepted_automatically']==[]
    assert all(row['status']=='needs_human_confirmation' for row in packet['candidates'])

def test_human_approval_creates_new_snapshot_and_rejects_bad_mapping(tmp_path):
    from app.manual_review import apply_hashoshanim_review
    from app.store import Store
    decisions={'decisions':[{'field':'units','proposed_value':'6','decision':'approve','note':''},{'field':'pilotis_area_m2','proposed_value':'148.50','decision':'reject','note':'מרפסות'}]}
    path=tmp_path/'review.json';path.write_text(json.dumps(decisions,ensure_ascii=False),encoding='utf8')
    store=Store(path=tmp_path/'db.sqlite3');store.init();d=apply_hashoshanim_review(path,store)
    assert d['fields']['units']['certainty']=='manually_verified'
    assert d['fields']['open_pilotis_area']['certainty']=='conflict'
    assert store.dossier(d['id'])['human_review']['accepted'][0]['field']=='units'

def test_batch_reports_missing_pdf_without_api(tmp_path):
    from app.pilot_batch import run_batch
    batch=tmp_path/'batch';batch.mkdir();(batch/'input').mkdir()
    (batch/'manifest.csv').write_text('local_filename,address,municipal_file_number,public_source_url,document_type,notes\nmissing.pdf,x,,,,\n',encoding='utf8')
    report=run_batch(batch)
    assert report['completed']==0 and report['failed']==1 and report['cost_usd']==0
    assert 'PDF missing' in report['documents'][0]['error']

def test_playwright_scraper_parses_public_archive_routes_only():
    from app.browser_scraper import _address,_archive_calls,_pdf_link,_allowed
    html='<div class="top-navbar-info-desc">כתובת:</div><div>הרב קוק 10 הרצליה</div><a href="javascript:showArchiveFile(2,19650106,0,1)">מסמך</a>'
    assert _address(html)=='הרב קוק 10 הרצליה'
    assert _archive_calls(html)==[(2,19650106,0,1)]
    assert _pdf_link('<a href="https://archive.gis-net.co.il/a.pdf">x</a>').endswith('/a.pdf')
    with pytest.raises(Exception,match='allowlist'):_allowed('https://example.com/a.pdf')

def test_archive_catalog_parser_and_resumable_store(store):
    from app.archive_catalog import parse_building_file
    html='''<div>כתובת: רחוב בדיקה 4 הרצליה</div><table><tr><th>מספר גוש</th><th>מספר חלקה</th></tr><tr><td>6529</td><td>167</td></tr></table><table><tr><th>מספר בקשה</th><th>תאריך</th></tr><tr><td>19700069</td><td>1/1/1970</td></tr></table>'''
    record={'id':'5848','html':html,'text':'כתובת: רחוב בדיקה 4 הרצליה\n','source':{'url':'https://example.org','retrieved_at':utcnow()}}
    parsed=parse_building_file(record)
    assert parsed['parcels']==[{'gush':6529,'parcel':167}] and parsed['requests']==[19700069]
    store.save_archive_street('1','בדיקה')
    store.save_archive_file('5848',{'discovered_on_streets':[{'code':'1','name':'בדיקה'}]})
    assert store.archive_status()['files']['discovered']==1
    store.save_archive_file('5848',parsed,'metadata_complete')
    assert store.archive_files_for_parcels([(6529,167)])[0]['address']=='רחוב בדיקה 4 הרצליה'
