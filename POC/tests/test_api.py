import pytest
from fastapi.testclient import TestClient
from shapely.geometry import mapping,box
from app.store import Store
from app.geo import itm
from app.config import SAMPLE_POLYGON
from app.sources import utcnow

@pytest.fixture
def client(tmp_path,monkeypatch):
    import app.main as main
    store=Store(url='',path=tmp_path/'api.sqlite')
    monkeypatch.setattr(main,'store',store)
    monkeypatch.setattr(main,'submit',lambda jid:None)
    monkeypatch.setattr(main.GovMap,'boundary',lambda self:{'geometry':mapping(itm(box(34.83,32.15,34.86,32.18))),'_source':{'url':'https://example.org/boundary','retrieved_at':utcnow()}})
    with TestClient(main.app) as c:yield c,store

def test_search_roundtrip_validation_and_retry(client):
    c,s=client
    assert c.get('/').status_code==200
    assert c.get('/static/vendor/leaflet.js').status_code==200
    result=c.post('/api/searches',json={'polygon':SAMPLE_POLYGON,'filters':{},'preferences':[]});assert result.status_code==202
    jid=result.json()['id'];assert c.get('/api/searches/'+jid).json()['state']=='queued'
    assert c.get('/api/package').json()['remaining']==3
    assert c.post('/api/searches',json={'polygon':mapping(box(0,0,1,1))}).status_code==422
    circle=c.post('/api/searches',json={'center':{'lat':32.165,'lon':34.845},'radius_m':100,'filters':{},'preferences':[]})
    assert circle.status_code==202 and c.get('/api/searches/'+circle.json()['id']).json()['request']['selection_seed'] is not None
    assert c.get('/api/dossiers/not-present').status_code==404
    s.update(jid,'failed',30,{'candidates':[]},'Source unavailable')
    assert c.post('/api/searches/'+jid+'/retry').json()['id']==jid

def test_real_sample_api_exports_and_no_profit_without_basis(client):
    c,s=client
    result=c.post('/api/pilot-sample');assert result.status_code==200
    if not result.json():pytest.skip('Source audit absent')
    d=result.json()[0]
    for kind,ctype in [('pdf','application/pdf'),('xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]:
        response=c.get('/api/dossiers/'+d['id']+'/export/'+kind);assert response.status_code==200;assert response.headers['content-type']==ctype
    a={'sale_area':100,'construction_area':150,'sale_price':10,'build_cost':2,'tenant_rent':5,'rent_months':10,'consultants':10,'finance':20,'levies_taxes':30,'parking':40,'reserve':50,'other_costs':0,'tax_basis':'all-inclusive','assumptions_note':'Explicit test assumptions only'}
    assert c.post('/api/dossiers/'+d['id']+'/scenarios',json=a).status_code==409
    assert c.get('/api/package').json()['remaining']==3

def test_hashoshanim_evidence_dossier(client):
    c,s=client
    response=c.post('/api/hashoshanim-sample');assert response.status_code==200
    d=response.json()
    assert d['fields']['building_file_number']['value']==5848
    assert d['fields']['units']['value']==6
    assert d['fields']['permit_date']['value']=='1970-04-12'
    assert d['fields']['existing_legal_area']['value']==578.59
    assert d['fields']['shaked_area_cap']['value']==2314.36
    assert d['fields']['tama70_zone']['value']=='מרחב עירוני מוטה מטרו — תא שטח 206'
    assert d['eligibility']['core_passed'] is True
    assert d['status']=='needs_verification'
    assert c.get('/api/package').json()['remaining']==3
    assert c.post('/api/hashoshanim-sample').json()['id']==d['id']
    assert c.get('/api/dossiers/'+d['id']+'/export/pdf').status_code==200
    assert c.get('/api/dossiers/'+d['id']+'/export/xlsx').status_code==200
