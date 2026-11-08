"""Synthetic PostgreSQL fixtures only; no live source or paid requests."""
import hashlib,json
import httpx,pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Part,Vehicle,DismantlingItem,Operation
from app.services.unified_catalogue import CatalogueAdapter,CatalogueResolver,CatalogueUnavailable


def envelope(car=107555,coverage='complete_verified'):
    p=dict(schema='carpot.volvo.v1',manufacturer_id=120,car_id=car,model_id=13084,
        modification={'id':car,'description':'T6 AWD'},collection_complete=True,reviewed_by='synthetic',coverage=coverage,
        observed_at='2026-11-08T12:00:00+00:00',categories=[dict(product_id=106,name_source='Bulb',name_uk='Лампа',mapping_reviewed_by='fixture',category_path=['Освітлення','Лампи','Лампа'],articles=['2:EXAMPLE'])],
        articles={'2:EXAMPLE':dict(supplier_id=2,article_number='EXAMPLE',supplier=[{'description':'HELLA'}],article=[{'NormalizedDescription':'Bulb'}],oem=[{'OENbr':'OEM-ONE'},{'OENbr':'OEM-TWO'}],images=[{'PictureName':'2_E325.JPG'}])})
    return dict(payload=p,sha256=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())

@pytest.fixture
def volvo(logged,monkeypatch):
    r=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90 II','year':2018,'donor_id':'SYNTHETIC'})
    assert r.status_code==201,r.text
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car:envelope(car))
    return r.json()

def create(c,v,car=107555):
    return c.post(f"/api/v1/vehicles/{v['id']}/unified-catalogue",json={'model_id':13084,'source_modification_id':car,'confirm_exact_modification':True})

def test_persistent_plan_no_stock_or_ktype(logged,volvo,monkeypatch):
    assert create(logged,volvo).json()['created']==1
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *a:pytest.fail('No request on reopen'))
    assert create(logged,volvo).json()['created']==0
    b=f"/api/v1/vehicles/{volvo['id']}"
    assert logged.get(b+'/unified-catalogue').json()['source_modification_id']==107555
    w=logged.get(b+'/dismantling-workspace?source=catalogue').json()
    assert len(w['items'])==1 and w['items'][0]['name']=='Лампа'
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==0
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type.in_(['receipt','sale','correction','reserve'])))==0
        assert db.get(Vehicle,volvo['id']).ktype is None

def test_receipt_retry_article_and_oem_separation(logged,volvo):
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    key=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['key']
    a=logged.get(b+'/unified-catalogue/articles',params={'key':key}).json()['articles'][0]
    assert a['oem_numbers']==['OEM-ONE','OEM-TWO'] and not a['vin_verified']
    for n in (1,0):
        r=logged.post(b+'/unified-catalogue/stock',json={'keys':[key],'confirm_physical_receipt':True})
        assert r.status_code==200,r.text
        assert r.json()['added']==n
    p=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['parts'][0]
    with Session(engine()) as db:
        part=db.get(Part,p['id']);part.selling_price=123.45;part.currency='USD';db.commit()
    r=logged.post(b+'/unified-catalogue/article',json={'key':key,'art_id':1,'part_id':p['id']})
    assert r.status_code==200,r.text
    with Session(engine()) as db:
        part=db.get(Part,p['id'])
        assert (part.article_number,part.article_brand,part.quantity)==('EXAMPLE','HELLA',1)
        assert not part.oem_number and str(part.selling_price)=='123.45' and part.currency=='USD'
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1
    assert create(logged,volvo,107556).status_code==409

def test_partial_no_plan_or_stock(logged,volvo,monkeypatch):
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car:envelope(car,'partial'))
    r=create(logged,volvo)
    assert r.status_code==200 and r.json()['source']=='base'
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(DismantlingItem))==0

def test_saved_pp_and_xc40_fallback():
    class Down:
        def plan(self,*a):raise CatalogueUnavailable()
    r=CatalogueResolver(Down()).resolve(make='Volvo',source_modification_id=107555,saved_plan_parts=True)
    assert r['source']=='saved_plan_parts' and r['cost']=='free'
    assert CatalogueResolver(Down()).resolve(make='Volvo')['source']=='base'

def test_base_explicit_receipt(logged,volvo):
    b=f"/api/v1/vehicles/{volvo['id']}"
    r=logged.post(b+'/unified-catalogue/base');assert r.status_code==200,r.text
    assert logged.get(b+'/unified-catalogue').json()['source']=='base'
    w=logged.get(b+'/dismantling-workspace?source=base').json()
    assert w['items']
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0
    for n in (1,0):
        r=logged.post(b+'/unified-catalogue/stock',json={'keys':[w['items'][0]['key']],'confirm_physical_receipt':True})
        assert r.status_code==200,r.text
        assert r.json()['added']==n

def test_existing_stock_protected(logged,volvo):
    assert logged.post('/api/v1/parts',json={'vehicle_id':volvo['id'],'name':'Ручна деталь'}).status_code==201
    assert create(logged,volvo).status_code==409

def test_account_isolation(logged,volvo,client):
    from conftest import signup
    assert create(logged,volvo).status_code==200
    logged.post('/api/v1/auth/logout');signup(client,'other-volvo@example.test')
    assert client.get(f"/api/v1/vehicles/{volvo['id']}/unified-catalogue").status_code==404

@pytest.mark.parametrize('origin',['http://catalogue.test','https://evil.test','https://catalogue.test@evil.test','https://catalogue.test/path','https://catalogue.test?x=1'])
def test_origin_guard(origin,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL',origin);monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','test-only')
    with pytest.raises(CatalogueUnavailable):CatalogueAdapter(transport=httpx.MockTransport(lambda r:pytest.fail('Network forbidden'))).plan(107555)

@pytest.mark.parametrize('response',[httpx.Response(302,headers={'location':'https://evil.test'}),httpx.Response(503),httpx.Response(200,json={'payload':{},'sha256':'fake'})])
def test_redirect_fault_contract(response,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL','https://catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','test-only')
    with pytest.raises(CatalogueUnavailable):CatalogueAdapter(transport=httpx.MockTransport(lambda r:response)).plan(107555)

@pytest.mark.parametrize('supplier_name,accepted',[('HELLA',True),('Other supplier',False)])
def test_enrichment_exact_supplier_and_oem_only(supplier_name,accepted,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL','https://catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','test-only')
    adapter=CatalogueAdapter(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=dict(supplier_id=2,article_number='EXAMPLE',supplier_name=supplier_name,oem_numbers=['OEM-A','OEM-B'],observed_at='2026-11-08T00:00:00Z'))))
    if accepted:
        r=adapter.article(2,'EXAMPLE','HELLA')
        assert r['fitment']=='cross_reference_only' and not r['vin_verified'] and r['photo'] is None
    else:
        with pytest.raises(CatalogueUnavailable):adapter.article(2,'EXAMPLE','HELLA')


def test_duplicate_modification_names_stay_separate(monkeypatch):
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL','https://catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','test-only')
    rows=[dict(model_id=13084,source_modification_id=i,modification={'description':'D5 AWD'}) for i in (107556,107557)]
    r=CatalogueAdapter(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'items':rows}))).modifications(13084)
    assert len(r['items'])==2 and r['items'][0]['source_modification_id']!=r['items'][1]['source_modification_id']


def test_wrong_model_and_unconfirmed_selection_rejected(logged,volvo):
    base=f"/api/v1/vehicles/{volvo['id']}/unified-catalogue"
    assert logged.post(base,json=dict(model_id=37773,source_modification_id=126478,confirm_exact_modification=True)).status_code==409
    assert logged.post(base,json=dict(model_id=13084,source_modification_id=107555)).status_code==422


def test_explicit_oem_cross_selection_and_manual_value_protected(logged,volvo):
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    key=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['key']
    assert logged.post(b+'/unified-catalogue/stock',json={'keys':[key],'confirm_physical_receipt':True}).status_code==200
    p=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['parts'][0]
    body=dict(key=key,art_id=1,part_id=p['id'],oem_number='FAKE',confirm_cross_reference=True)
    assert logged.post(b+'/unified-catalogue/oem',json=body).status_code==422
    body['oem_number']='OEM-ONE'
    assert logged.post(b+'/unified-catalogue/oem',json=body).status_code==200
    body['oem_number']='OEM-TWO'
    assert logged.post(b+'/unified-catalogue/oem',json=body).status_code==409
    with Session(engine()) as db:
        p=db.get(Part,p['id'])
        assert p.oem_number=='OEM-ONE' and p.oem_provenance['vin_verified'] is False


def test_manual_rename_survives_reopen(logged,volvo,monkeypatch):
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    key=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['key']
    r=logged.post(b+'/dismantling-workspace/annotations',json={'source':'catalogue','keys':[key],'action':'rename','name':'Перевірена лампа власника'})
    assert r.status_code==200,r.text
    assert create(logged,volvo).json()['created']==0
    assert logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['name']=='Перевірена лампа власника'


def test_concurrent_receipt_is_one_physical_position(logged,volvo):
    from concurrent.futures import ThreadPoolExecutor
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    key=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['key']
    def add():return logged.post(b+'/unified-catalogue/stock',json={'keys':[key],'confirm_physical_receipt':True})
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:add(),range(2)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert sum(r.json()['added'] for r in responses)==1
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==1
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1


def test_changed_vehicle_keeps_plan_but_blocks_stale_receipt(logged,volvo):
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    key=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['key']
    with Session(engine()) as db:
        v=db.get(Vehicle,volvo['id']);v.ktype=999;db.commit()
    assert logged.get(b+'/unified-catalogue').json()['review_required'] is True
    assert logged.get(b+'/dismantling-workspace?source=catalogue').json()['items']
    assert logged.post(b+'/unified-catalogue/stock',json={'keys':[key],'confirm_physical_receipt':True}).status_code==409
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0
