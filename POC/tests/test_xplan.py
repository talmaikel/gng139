import pytest
from shapely.geometry import box,mapping,Point

from app.sources import utcnow
from app.store import Store
from app.xplan import XPlanCatalog,XPlanScreen,combine_screenings,resolve_with_archive
from app.rules import evaluate,evidence,eligibility_status

def feature(geometry,**props):return {'type':'Feature','geometry':mapping(geometry),'properties':props}
def plan(pid='p1',number='100',status='התכנית אושרה',name='תכנית מגורים'):
    return feature(box(-5,-5,15,15),objectid=100,pl_id=pid,pl_number=number,pl_name=name,
                   station_desc='אישור',internet_short_status=status,entity_subtype_desc='תכנית מפורטת',
                   plan_charactor_name='תכנית שמכוחה ניתן להוציא היתרים',pl_objectives=name)
def land(code,name='מגורים א',geometry=None,pid='p1',oid=1):
    return feature(geometry or box(0,0,10,10),objectid=oid,pl_id=pid,pl_number='100',pl_name='תכנית',mavat_code=code,mavat_name=name,station_desc='אישור')
def snapshot(landuse,plans=None,points=None,polygons=None):
    return {'id':'snap','created_at':utcnow(),'layers':{'landuse':landuse,'plans':plans or [plan()],'points':points or [],'polygons':polygons or []}}
def parcel():return feature(box(0,0,10,10),GUSH_NUM=1,GUSH_SUFFI=0,PARCEL=2)

def test_residential_and_nonresidential_thresholds():
    assert XPlanScreen(snapshot([land(10)])).screen(parcel())['category']=='primary_candidate'
    rejected=XPlanScreen(snapshot([land(500,'מבנים ומוסדות ציבור')])).screen(parcel())
    assert rejected['category']=='filtered_landuse' and not rejected['queue_eligible']
    partial=XPlanScreen(snapshot([land(500,'מסחר',box(0,0,5,10))])).screen(parcel())
    assert partial['category']=='needs_verification' and partial['queue_eligible']
    assert XPlanScreen(snapshot([land(995,'יעוד לפי תכנית מאושרת אחרת')])).screen(parcel())['category']=='needs_verification'

def test_unapproved_never_filters_and_conflicts_require_verification():
    pending=plan(status='הפקדה')
    row=XPlanScreen(snapshot([land(500,'מסחר')],[pending])).screen(parcel())
    assert row['category']=='needs_verification' and row['warnings']
    p2=plan('p2','200');mixed=XPlanScreen(snapshot([land(10),land(500,'מסחר',pid='p2',oid=2)],[plan(),p2])).screen(parcel())
    assert mixed['category']=='needs_verification'

def test_special_routes_and_compound_are_not_download_queue():
    # Tama 70's citywide code 808 zone must not tag metro on its own; only station markers within the buffer do.
    tod=XPlanScreen(snapshot([land(10),land(808,'מרחב עירוני מוטה מטרו',pid='p2',oid=9)],[plan(),plan('p2','200')])).screen(parcel())
    assert tod['category']!='metro'
    station=feature(Point(300,5),objectid=4,pl_id='p1',pl_number='100',mavat_code=6022,mavat_name='כניסה/ יציאה לתחנת מטרו',station_desc='אישור')
    metro=XPlanScreen(snapshot([land(10)],points=[station])).screen(parcel())
    assert metro['category']=='metro' and not metro['queue_eligible'] and metro['metro_stations'][0]['distance_m']==290
    far=feature(Point(600,5),objectid=5,pl_id='p1',pl_number='100',mavat_code=6022,mavat_name='כניסה/ יציאה לתחנת מטרו',station_desc='אישור')
    assert XPlanScreen(snapshot([land(10)],points=[far])).screen(parcel())['category']=='primary_candidate'
    preservation=feature(Point(5,5),objectid=3,pl_id='p1',pl_number='100',mavat_code=710,mavat_name='מבנה לשימור',station_desc='אישור')
    assert XPlanScreen(snapshot([land(10)],points=[preservation])).screen(parcel())['category']=='preservation'
    renewal=plan(name='תכנית פינוי בינוי והתחדשות עירונית')
    assert XPlanScreen(snapshot([land(10)],[renewal])).screen(parcel())['category']=='existing_renewal_plan'
    combined=combine_screenings([XPlanScreen(snapshot([land(10)])).screen(parcel())],3,1)
    assert combined['category']=='urban_renewal_compound' and not combined['queue_eligible']

def test_archive_designation_resolves_995_but_never_demotes():
    from app.archive_catalog import archive_designation,parse_request_page
    ambiguous=XPlanScreen(snapshot([land(995,'יעוד לפי תכנית מאושרת אחרת')])).screen(parcel())
    assert ambiguous['ambiguous_only'] and ambiguous['category']=='needs_verification'
    combined=combine_screenings([ambiguous],1,1)
    html='<table><tr><th>מספר גוש</th><th>מספר חלקה</th><th>מספר מגרש</th><th>יעוד</th></tr><tr><td>1</td><td>2</td><td></td><td>דרך מוצעת</td></tr><tr><td>1</td><td>2</td><td></td><td>מגורים ב</td></tr></table>'
    page=parse_request_page(html);assert page['designations']==['דרך מוצעת','מגורים ב']
    residential={'file_number':5,'address':'x','designations':page['designations'],'designation_source':{'url':'https://example.org/permit'}}
    promoted=resolve_with_archive(combined,[residential],archive_designation)
    assert promoted['category']=='primary_candidate' and promoted['queue_eligible'] and promoted['archive_resolution'][0]['basis']=='permit_page'
    assert any('רצועת דרך' in w for w in promoted['warnings'])
    commercial={'file_number':6,'designations':['מסחר'],'designation_source':{'url':'u'}}
    kept=resolve_with_archive(combined,[commercial],archive_designation)
    assert kept['category']=='needs_verification' and not kept.get('tags',[]).count('archive_resolved_995')
    from_plans={'file_number':7,'plans':[{'number':'1192','name':"מגורים ב'",'status':'בתוקף'}],'source':{'url':'u'}}
    assert resolve_with_archive(combined,[from_plans],archive_designation)['archive_resolution'][0]['basis']=='plans_list'
    concrete=XPlanScreen(snapshot([land(500,'מסחר')])).screen(parcel())
    assert resolve_with_archive(combine_screenings([concrete],1,1),[residential],archive_designation)['category']=='filtered_landuse'

def test_scope_rule_routes_instead_of_failing():
    src={'url':'https://example.org','retrieved_at':utcnow()}
    checks=evaluate({'scope_parcels':evidence(3,src,'official','page 2','test')},{})
    assert next(x for x in checks if x['id']=='scope_parcels')['status']=='routed'
    assert eligibility_status(checks)=='urban_renewal_compound'

def test_snapshot_and_screening_persistence(tmp_path):
    store=Store(url='',path=tmp_path/'db.sqlite');store.init();snap=snapshot([land(10)]);store.save_xplan_snapshot(snap)
    row=XPlanScreen(snap).screen(parcel());store.save_parcel_screening(row)
    assert store.latest_xplan_snapshot()['id']=='snap'
    assert store.parcel_screening(row['parcel_key'])['category']=='primary_candidate'
    assert store.xplan_status()['categories']=={'primary_candidate':1}

def test_feature_batches_are_complete_and_bounded():
    class Stub:
        def __init__(self):self.sizes=[]
        def json(self,path,params,ttl=None):
            ids=[int(x) for x in params['objectIds'].split(',')];self.sizes.append(len(ids))
            return {'features':[feature(box(0,0,1,1),objectid=i) for i in ids]},{'url':'test'}
    client=Stub();rows,_=XPlanCatalog(client)._features(4,list(range(1001)))
    # Batches stay small so the encoded query URL remains under the ~2100-char limit the XPlan front end enforces.
    assert len(rows)==1001 and client.sizes==[150]*6+[101]
