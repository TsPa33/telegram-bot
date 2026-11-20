"""Synthetic PostgreSQL fixtures only; no live source or paid requests."""
import hashlib,json
import httpx,pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Part,Vehicle,DismantlingItem,Operation
from app.services.unified_catalogue import CatalogueAdapter,CatalogueResolver,CatalogueUnavailable


def detail_items():
    return [dict(supplier_id=2,article_number='EXAMPLE',car_id=107555,supplier=[{'description':'HELLA'}],article=[{'NormalizedDescription':'Bulb'}],oem=[{'manufacturerId':120,'OENbr':'OEM-ONE'},{'manufacturerId':120,'OENbr':'OEM-TWO'}],images=[{'PictureName':'2_E325.JPG'}])]


def envelope(car=107555,coverage='complete_verified'):
    p=dict(schema='carpot.volvo.plan.v2',manufacturer_id=120,car_id=car,model_id=13084,
        modification={'id':car,'description':'T6 AWD'},coverage_verified=coverage=='complete_verified',taxonomy_status='reviewed',coverage=coverage,
        source_snapshot_sha='a'*64,observed_at='2026-11-08T12:00:00+00:00',
        categories=[dict(product_id=106,name_source='Bulb',name_uk='Лампа',kind='part',mapping_reviewed_by='fixture',category_path=['Освітлення','Передні фари','Лампа'],article_count=1)])
    return dict(payload=p,sha256=hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())

@pytest.fixture
def volvo(logged,monkeypatch):
    r=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90 II','year':2018,'donor_id':'SYNTHETIC'})
    assert r.status_code==201,r.text
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car:envelope(car))
    monkeypatch.setattr(CatalogueAdapter,'articles',lambda *args,**kwargs:detail_items())
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


def test_new_donor_stores_compact_plan_not_raw_article_blob(logged,volvo,monkeypatch):
    e=envelope()
    e['payload']['articles']={'private_blob':'SYNTHETIC '*350000}
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *args:e)
    assert create(logged,volvo).status_code==200
    with Session(engine()) as db:
        state=db.get(Vehicle,volvo['id']).dismantling_v3['unified_catalogue']
        assert len(json.dumps(state).encode())<10000
        assert 'articles' not in state['payload'] and 'details' not in state['payload']
        assert state['payload']['source_snapshot_sha']=='a'*64


def test_reviewed_taxonomy_does_not_override_partial_coverage():
    class Adapter:
        def plan(self,*args):
            e=envelope();e['payload']['coverage_verified']=False
            return e
    r=CatalogueResolver(Adapter()).resolve(make='Volvo',source_modification_id=107555,saved_plan_parts=True)
    assert r['source']=='saved_plan_parts' and r['cost']=='free'


def test_detail_outage_does_not_break_saved_plan_or_write_articles(logged,volvo,monkeypatch):
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    key=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]['key']
    calls=[]
    def down(*args):
        calls.append(args[1:]);raise CatalogueUnavailable()
    monkeypatch.setattr(CatalogueAdapter,'articles',down)
    assert logged.get(b+'/unified-catalogue').status_code==200
    assert logged.get(b+'/dismantling-workspace?source=catalogue').status_code==200
    assert not calls
    assert logged.get(b+'/unified-catalogue/articles',params={'key':key}).status_code==503
    assert calls==[(107555,106,'a'*64)]
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0


@pytest.mark.parametrize('reply_sha,reply_car', [('b'*64,107555),('a'*64,107556)])
def test_details_never_fall_back_to_latest_or_other_car(reply_sha,reply_car,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL','https://catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','test-only')
    seen=[]
    def respond(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200,json=dict(snapshot_sha=reply_sha,car_id=reply_car,product_id=106,items=detail_items()))
    adapter=CatalogueAdapter(transport=httpx.MockTransport(respond))
    with pytest.raises(CatalogueUnavailable):adapter.articles(107555,106,'a'*64)
    assert seen==[{'product_id':'106','snapshot_sha':'a'*64}]


def test_non_part_classification_cannot_create_stock(logged,volvo,monkeypatch):
    e=envelope();e['payload']['categories'][0]['kind']='consumable'
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *args:e)
    assert create(logged,volvo).status_code==200
    b=f"/api/v1/vehicles/{volvo['id']}"
    row=logged.get(b+'/dismantling-workspace?source=catalogue').json()['items'][0]
    assert row['kind']=='consumable'
    assert logged.post(b+'/unified-catalogue/stock',json={'keys':[row['key']],'confirm_physical_receipt':True}).status_code==409
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0


def test_adapter_consumes_compact_real_shape_not_private_source(monkeypatch):
    import importlib.util
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    def load(name,path):
        spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    contract=load('catalogue_contract_fixture',root/'catalogue/volvo_contract.py')
    fixtures=load('catalogue_shape_fixture',root/'catalogue/tests/volvo_shape_fixture.py')
    raw=fixtures.fixture(padded=True)
    compact=contract.compact_plan(raw,contract.digest(raw))
    wire=dict(payload=compact,sha256=contract.digest(compact))
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL','https://catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.test');monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','test-only')
    adapter=CatalogueAdapter(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=wire)))
    plan=adapter.plan(107555)
    assert len(plan['payload']['categories'])==113
    assert len(json.dumps(plan).encode())<50000
    assert CatalogueResolver(adapter).resolve(make='Volvo',source_modification_id=107555,saved_plan_parts=True)['source']=='saved_plan_parts'


@pytest.mark.parametrize("car,manufacturer",[(107555,120),(900,77)])
def test_global_partial_create_reopen_and_article_without_legacy(logged, monkeypatch,car,manufacturer):
    source=envelope(car,coverage='partial')
    source['payload']['manufacturer_id']=manufacturer
    if manufacturer!=120:source['payload']['schema']='carpot.vehicle.plan.v1'
    source['payload']['taxonomy_status']='draft'
    source['payload']['categories'][0].update(name_uk=None,category_path=[None,None,None],mapping_reviewed_by=None)
    prototype=source['payload']['categories'][0]
    source['payload']['categories']=[dict(prototype,product_id=106+i,name_source=f'Synthetic type {i}') for i in range(113)]
    def plan(self,car,**kwargs):
        assert kwargs.get('global_source') is True
        return source
    monkeypatch.setattr(CatalogueAdapter,'plan',plan)
    monkeypatch.setattr(CatalogueAdapter,'directory',lambda self,after=0,**kwargs:dict(items=[dict(source_modification_id=car,model_id=13084,manufacturer_id=manufacturer,manufacturer='Synthetic source brand',model='Synthetic source model',generation=None,snapshot_sha='a'*64)],next_after=None))
    monkeypatch.setattr(CatalogueAdapter,'articles',lambda *args,**kwargs:detail_items())
    monkeypatch.setattr(CatalogueResolver,'resolve',lambda *a,**kw:pytest.fail('Legacy resolver forbidden'))
    from app.services import dismantling
    monkeypatch.setattr(dismantling,'start',lambda *a,**kw:pytest.fail('Base forbidden'))
    body=dict(request_key='11111111-1111-1111-1111-111111111111',source_modification_id=car,year=2018)
    r=logged.post('/api/v1/vehicles/catalogue-directory/vehicles',json=body)
    assert r.status_code==201,r.text
    v=r.json();base=f"/api/v1/vehicles/{v['id']}/global-dismantling"
    assert logged.post('/api/v1/vehicles/catalogue-directory/vehicles',json=body).json()['id']==v['id']
    assert logged.post(base).status_code==200
    state=logged.get(base).json()
    assert state['saved']['payload']['coverage']=='partial'
    key=state['keys']['106']
    assert logged.get(f"/api/v1/vehicles/{v['id']}/unified-catalogue/articles",params={'key':key}).json()['articles'][0]['oem_numbers']==['OEM-ONE','OEM-TWO']
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *a,**kw:pytest.fail('Saved plan must reopen offline'))
    assert logged.post(base).json()['created']==0
    assert logged.get(base).json()['saved']==state['saved']
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==0
        assert db.scalar(select(func.count()).select_from(Vehicle))==1
        assert db.scalar(select(func.count()).select_from(DismantlingItem))==113


def test_global_rejects_missing_links_and_preserves_old(logged,volvo,monkeypatch):
    assert logged.post(f"/api/v1/vehicles/{volvo['id']}/global-dismantling").status_code==409
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *a,**kw:envelope())
    monkeypatch.setattr(CatalogueAdapter,'directory',lambda *a,**kw:dict(items=[],next_after=None))
    r=logged.post('/api/v1/vehicles/catalogue-directory/vehicles',json=dict(request_key='22222222-2222-2222-2222-222222222222',source_modification_id=107555,year=2018))
    assert r.status_code==409,r.text
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Vehicle))==1


def test_volvo_oem_preview_preserves_existing_plan(logged,volvo,monkeypatch):
    base=f"/api/v1/vehicles/{volvo['id']}"
    assert logged.post(base+'/unified-catalogue/base').status_code==200
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car:envelope(car,'partial'))
    from app.services.inventory import snapshot
    def state():
        with Session(engine()) as db:
            return (snapshot(db.get(Vehicle,volvo['id'])),
                    [snapshot(r) for r in db.scalars(select(DismantlingItem).order_by(DismantlingItem.id))],
                    db.scalar(select(func.count()).select_from(Part)),
                    db.scalar(select(func.count()).select_from(Operation)))
    before=state()
    url=base+'/volvo-oem-preview'
    r=logged.get(url,params={'source_modification_id':107555})
    assert r.status_code==200,r.text
    data=r.json()
    assert data['coverage']=='partial' and data['vin_verified'] is False
    assert data['plan_items'] and data['catalogue_types'][0]['product_id']==106
    query=dict(source_modification_id=107555,product_id=106,snapshot_sha=data['snapshot_sha'])
    detail=logged.get(url,params=query)
    assert detail.status_code==200,detail.text
    assert detail.json()['articles'][0]['oem_numbers']==['OEM-ONE','OEM-TWO']
    assert logged.get(url,params={**query,'snapshot_sha':'b'*64}).status_code==409
    assert logged.get(url,params={**query,'product_id':999}).status_code==404
    assert logged.get(url,params={'source_modification_id':107555,'product_id':106}).status_code==422
    assert logged.get(url,params={'source_modification_id':107556}).status_code==422
    assert state()==before

def test_volvo_oem_preview_wrong_brand_and_workspace(logged,volvo,client):
    other=logged.post('/api/v1/vehicles',json={'manufacturer':'Peugeot','model':'3008','year':2017,'donor_id':'OTHER'}).json()
    assert logged.get(f"/api/v1/vehicles/{other['id']}/volvo-oem-preview",params={'source_modification_id':107555}).status_code==409
    from conftest import signup
    logged.post('/api/v1/auth/logout')
    signup(client,'other-oem-preview@example.test')
    assert client.get(f"/api/v1/vehicles/{volvo['id']}/volvo-oem-preview",params={'source_modification_id':107555}).status_code==404


def test_volvo_oem_selection_plan_then_stock(logged,volvo,monkeypatch):
    from app.services.inventory import snapshot
    from uuid import uuid4
    base=f"/api/v1/vehicles/{volvo['id']}"
    assert logged.post(base+'/unified-catalogue/base').status_code==200
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car:envelope(car,'partial'))
    offers=detail_items()
    offers[0]['oem'] += [{'manufacturerId':80,'OENbr':'OTHER-MAKE'},{'OENbr':'UNKNOWN-MAKE'}]
    monkeypatch.setattr(CatalogueAdapter,'articles',lambda *a,**kw:offers)
    def preview():
        r=logged.get(base+'/volvo-oem-preview',params={'source_modification_id':107555})
        assert r.status_code==200,r.text
        return r.json()
    def body(data,row,**kwargs):
        return dict(request_key=str(uuid4()),source_modification_id=107555,snapshot_sha=data['snapshot_sha'],
            expected_vehicle_basis=data['vehicle_basis'],item_id=row['id'],expected_row_basis=row['row_basis'],
            expected_reference_digest=row['reference_digest'],product_id=106,supplier_id=2,
            article_number='EXAMPLE',oem_number='OEM-ONE',confirm_reference=True,**kwargs)
    url=base+'/volvo-oem-selection'
    data=preview();row=data['plan_items'][0]
    detail=logged.get(base+'/volvo-oem-preview',params={'source_modification_id':107555,
        'product_id':106,'snapshot_sha':data['snapshot_sha']}).json()
    assert detail['articles'][0]['oem_numbers']==['OEM-ONE','OEM-TWO']
    assert logged.post(url,json={**body(data,row),'oem_number':'OTHER-MAKE'}).status_code==422
    assert logged.post(url,json={**body(data,row),'confirm_reference':False}).status_code==422
    assert logged.post(url,json=body(data,row,assign_stock=True,confirm_physical_oem=True)).status_code==409
    with Session(engine()) as db:
        before=[snapshot(x) for x in db.scalars(select(DismantlingItem).order_by(DismantlingItem.id))]
    request=body(data,row)
    result=logged.post(url,json=request)
    assert result.status_code==200,result.text
    assert result.json()['stock_assigned'] is False
    tree=logged.get(base+'/assemblies').json()
    assert next(x for x in tree['items'] if x['id']==row['id'])['reference_oem']=='OEM-ONE'
    assert logged.post(url,json=request).json()==result.json()
    assert logged.post(url,json=body(data,row)).status_code==409
    with Session(engine()) as db:
        assert [snapshot(x) for x in db.scalars(select(DismantlingItem).order_by(DismantlingItem.id))]==before
        assert db.scalar(select(func.count()).select_from(Part))==0
    key='base:'+row['id']
    assert logged.post(base+'/unified-catalogue/stock',json={'keys':[key],'confirm_physical_receipt':True}).status_code==200
    data=preview();row=next(x for x in data['plan_items'] if x['id']==row['id'])
    assert row['reference']['oem_number']=='OEM-ONE' and not row['stock_eligible']
    tree=logged.get(base+'/assemblies').json()
    assert next(x for x in tree['items'] if x['id']==row['id'])['stock_oem']=='OEM-ONE'
    card=logged.get('/api/v1/parts/'+row['part_id']).json()
    assert card['oem_number']=='OEM-ONE'
    with Session(engine()) as db:
        p=db.get(Part,row['part_id'])
        assert p.oem_number=='OEM-ONE'
        assert p.oem_provenance['product_id']==106
        assert p.oem_provenance['physical_number_confirmed_by_user'] is False
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1
        # Simulate a card received by the previous version before legacy copy worked.
        p.oem_number='';p.oem_provenance={};db.commit()
        aid=p.account_id
    from app.services.auto_oem import enrich_vehicle
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *a,**kw:pytest.fail('Saved reference needs no plan request'))
    assert enrich_vehicle(engine(),aid,volvo['id'])==1
    with Session(engine()) as db:
        assert db.get(Part,row['part_id']).oem_number=='OEM-ONE'
    with Session(engine()) as db:
        v=db.get(Vehicle,volvo['id']);v.year=2019;db.commit()
    assert logged.post(url,json=body(data,row)).status_code==409


def test_volvo_real_export_review_is_exact_version_and_label():
    from app.services.volvo_oem_review import overlay, SOURCE_SHA, candidates
    from types import SimpleNamespace
    raw=dict(source_snapshot_sha=SOURCE_SHA,categories=[
        dict(product_id=2,name_source='Стартер',kind='review',article_count=12),
        dict(product_id=4,name_source='Wrong label',kind='review',article_count=13),
        dict(product_id=3224,name_source='Моторное масло',kind='review',article_count=21)])
    reviewed=overlay(raw)
    assert reviewed['categories'][0]['kind']=='part'
    assert reviewed['categories'][0]['name_uk']=='Стартер'
    assert reviewed['categories'][0]['pilot_reviewed']
    assert reviewed['categories'][1]['kind']=='review'
    assert reviewed['categories'][2]['kind']=='review'
    assert raw['categories'][0]['kind']=='review'
    assert candidates(SimpleNamespace(name='стартер'),reviewed['categories'])==[2]
    assert candidates(SimpleNamespace(name='Стартер у зборі'),reviewed['categories'])==[]
    assert overlay({**raw,'source_snapshot_sha':'b'*64})['categories'][0]['kind']=='review'


def test_volvo_pilot_rejects_confirmed_different_source(logged,volvo,monkeypatch):
    with Session(engine()) as db:
        v=db.get(Vehicle,volvo['id'])
        v.dismantling_v3={'global_selection':{'car_id':107556}}
        db.commit()
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *a,**kw:pytest.fail('Conflicting selection must not call Catalogue'))
    r=logged.get(f"/api/v1/vehicles/{volvo['id']}/volvo-oem-preview",params={'source_modification_id':107555})
    assert r.status_code==409,r.text


def test_automatic_oem_backfill_and_receipt(logged,volvo,monkeypatch):
    from app.services.auto_oem import enrich_vehicle,SourceCache,source_identity
    from app.services.inventory import snapshot
    base=f"/api/v1/vehicles/{volvo['id']}"
    assert create(logged,volvo).status_code==200
    with Session(engine()) as db:
        v=db.get(Vehicle,volvo['id'])
        target=db.scalar(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id))
        aid=v.account_id;rid=target.id;vid=v.id
        before=[snapshot(target)]
        assert source_identity(v)[0]==107555
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car,**kw:envelope(car))
    assert enrich_vehicle(engine(),aid,vid)==1
    assert enrich_vehicle(engine(),aid,vid)==0
    with Session(engine()) as db:
        v=db.get(Vehicle,vid);ref=v.dismantling_v3['volvo_oem_references'][rid]
        assert ref['oem_number']=='OEM-ONE' and len(ref['alternatives'])==2 and not ref['vin_verified']
        assert [snapshot(x) for x in db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==vid).order_by(DismantlingItem.id))]==before
        assert db.scalar(select(func.count()).select_from(Part))==0
    assert logged.patch(base+'/oem/'+rid,json={'expected_oem':'OEM-ONE','oem_number':'WRONG'}).status_code==422
    assert logged.patch(base+'/oem/'+rid,json={'expected_oem':'OEM-ONE','oem_number':'OEM-TWO'}).status_code==200
    assert logged.patch(base+'/oem/'+rid,json={'expected_oem':'OEM-ONE','oem_number':'OEM-TWO'}).status_code==409
    assert enrich_vehicle(engine(),aid,vid)==0
    assert logged.post(base+'/unified-catalogue/stock',json={'keys':['catalogue:'+rid],'confirm_physical_receipt':True}).status_code==200
    with Session(engine()) as db:
        p=db.get(Part,db.get(DismantlingItem,rid).part_id)
        assert p.oem_number=='OEM-TWO' and p.quantity==1 and not p.oem_provenance['vin_verified']
        assert len(p.oem_provenance['alternatives'])==2
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1

def test_automatic_oem_does_not_guess_other_modifications(logged,volvo):
    from app.services.auto_oem import source_identity
    with Session(engine()) as db:
        v=db.get(Vehicle,volvo['id']);assert source_identity(v) is None
        v.year=2016;v.vin='YV4A22PK2G1092943';v.fuel_type='diesel'
        assert source_identity(v) is None
        v.fuel_type='petrol';v.manufacturer='Peugeot'
        assert source_identity(v) is None
        v.dismantling_v3={'global_selection':{'car_id':88,'model_id':9,'manufacturer_id':7,'source_snapshot_sha':'b'*64,
            'vehicle_basis':__import__('app.services.unified_catalogue',fromlist=['vehicle_basis']).vehicle_basis(v)}}
        assert source_identity(v)==(88,9,7,'b'*64,True)


def test_automatic_oem_all_makes_exact_article_without_snapshot(logged,monkeypatch):
    from app.services.auto_oem import enrich_vehicle
    from app.services.inventory import snapshot
    v=logged.post('/api/v1/vehicles',json={'manufacturer':'Peugeot','model':'3008','year':2017}).json()
    p=logged.post('/api/v1/parts',json={'name':'Стартер','vehicle_id':v['id'],'article_number':'P-EXACT','selling_price':'123.45'}).json()
    with Session(engine()) as db:
        part=db.get(Part,p['id']);part.article_brand='BOSCH';part.quantity=1;db.commit()
        aid=part.account_id;before=snapshot(part)
    monkeypatch.setattr(CatalogueAdapter,'exact_oem',lambda self,make,brand,article,sid=None:dict(
        manufacturer=make,manufacturer_id=88,supplier_id=22,supplier_name=brand,article_number=article,oem_numbers=['P-002','P-001']))
    assert enrich_vehicle(engine(),aid,v['id'])==1
    assert enrich_vehicle(engine(),aid,v['id'])==0
    with Session(engine()) as db:
        part=db.get(Part,p['id']);after=snapshot(part)
        assert part.oem_number=='P-001' and part.oem_provenance['oem_manufacturer_id']==88
        assert {k:x for k,x in before.items() if k not in ('oem_number','oem_provenance')}=={k:x for k,x in after.items() if k not in ('oem_number','oem_provenance')}
    r=logged.patch('/api/v1/parts/'+p['id']+'/characteristics',json={'expected':{'oem_number':'P-001'},'values':{'oem_number':'P-002'}})
    assert r.status_code==200,r.text
    assert len(r.json()['oem_provenance']['alternatives'])==2
    assert enrich_vehicle(engine(),aid,v['id'])==0
    with Session(engine()) as db:assert db.get(Part,p['id']).oem_number=='P-002'


def test_auto_oem_placement_filters_opposite_and_unknown():
    from app.services.auto_oem import choices
    from types import SimpleNamespace
    def offer(number,position):
        return dict(brand='BOSCH',article_nr=number,supplier_id=2,oem_numbers=[number],
            source_attributes=[{'id':100,'description':'Сторона установки','displayvalue':position}] if position else [])
    row=SimpleNamespace(name='Амортизатор',position='передня ліва')
    product={'name_uk':'Амортизатор'}
    offers=[offer('REAR','задний мост слева'),offer('RIGHT','передний мост справа'),offer('OK','передний мост слева'),offer('UNKNOWN','')]
    assert [a['oem_number'] for a in choices(offers,row=row,product=product)]==['OK']

def test_auto_oem_directory_stably_ranks_matching_modifications():
    from types import SimpleNamespace
    from app.services.auto_oem import SourceCache
    v=SimpleNamespace(manufacturer='Peugeot',model='3008',generation='II',engine_code='EP6 FDT',year=2017,
        fuel_type='petrol',drive_type='fwd',engine_variant='',engine_displacement_l=1.6)
    entry=dict(manufacturer='PEUGEOT',model='3008 II',source_modification_id=88,model_id=9,manufacturer_id=7,
        snapshot_sha='b'*64,modification={'description':'1.6 THP'},specifications=[
            {'attributetype':'EngineCode','displayvalue':'EP6FDT'},
            {'attributetype':'ConstructionInterval','displayvalue':'2016 - 2020'},
            {'attributetype':'FuelType','displayvalue':'бензин'},
            {'attributetype':'DriveType','displayvalue':'передний привод'},
            {'attributetype':'Capacity','displayvalue':'1.6 l'}])
    cache=SourceCache();cache.directory=[entry]
    assert cache.resolve_directory(v)==(88,9,7,'b'*64,True)
    cache.directory.insert(0,{**entry,'source_modification_id':89})
    assert cache.resolve_directory(v)==(88,9,7,'b'*64,True)
    # A conflicting VIN decoder value must not prevent a clearly labelled
    # auto_assumed catalogue variant; it does not claim VIN-verified fitment.
    v.engine_code='CONFLICTING'
    assert cache.resolve_directory(v)==(88,9,7,'b'*64,True)
    v.engine_code='EP6 FDT'
    cache.directory=[entry];v.year=2014;assert cache.resolve_directory(v) is None


def test_vin_donor_automatically_gets_plan_oem_and_stock_carryover(logged, monkeypatch):
    from app.services.auto_oem import automatic_identity, enrich_vehicle

    response=logged.post('/api/v1/vehicles',json={
        'manufacturer':'Volvo','model':'XC90 II','year':2016,'vin':'YV4A22PK2G1092943',
        'engine_code':'B4204T27','fuel_type':'petrol','drive_type':'AWD',
    })
    assert response.status_code==201,response.text
    vehicle_id=response.json()['id']
    with Session(engine()) as db:
        aid=db.get(Vehicle,vehicle_id).account_id
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car,**kw:envelope(car))
    monkeypatch.setattr(CatalogueAdapter,'articles',lambda *a,**kw:detail_items())

    assert enrich_vehicle(engine(),'other-workspace',vehicle_id)==0
    assert enrich_vehicle(engine(),aid,vehicle_id)==1
    assert enrich_vehicle(engine(),aid,vehicle_id)==0
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle_id)
        assert automatic_identity(v)['car_id']==107555
        row=db.scalar(select(DismantlingItem))
        assert row.catalog_key=='car:107555:product:106'
        assert db.scalar(select(func.count()).select_from(DismantlingItem))==1
        assert db.scalar(select(func.count()).select_from(Part))==0
        v.engine_variant='changed'
        assert automatic_identity(v) is None
        row_id=row.id

    base=f"/api/v1/vehicles/{vehicle_id}"
    assert logged.get(base+'/global-dismantling').json()['oems']['106']['oem_number']=='OEM-ONE'
    assert logged.post(base+'/unified-catalogue/stock',json={
        'keys':['catalogue:'+row_id],'confirm_physical_receipt':True,
    }).status_code==200
    with Session(engine()) as db:
        part=db.scalar(select(Part))
        assert part.oem_number=='OEM-ONE'
        assert part.oem_provenance['source_modification_id']==107555
        assert part.oem_provenance['source_article']=='EXAMPLE'
        assert part.oem_provenance['retrieved_at']


def test_automatic_plan_preserves_existing_rows(logged, volvo, monkeypatch):
    from app.services.auto_oem import enrich_vehicle

    base=f"/api/v1/vehicles/{volvo['id']}"
    assert logged.post(base+'/unified-catalogue/base').status_code==200
    with Session(engine()) as db:
        aid=db.get(Vehicle,volvo['id']).account_id
        previous=set(db.scalars(select(DismantlingItem.id)))
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car,**kw:envelope(car))
    monkeypatch.setattr('app.services.auto_oem.SourceCache.resolve_directory',
                        lambda self,v:(107555,13084,120,'a'*64,True))

    assert enrich_vehicle(engine(),aid,volvo['id'])==0
    with Session(engine()) as db:
        assert set(db.scalars(select(DismantlingItem.id)))==previous
        assert db.scalar(select(func.count()).select_from(Part))==0


def test_automatic_oem_requires_stable_product_key():
    from types import SimpleNamespace
    from app.services.auto_oem import matches
    product={'kind':'part','name_uk':'Лампа'}
    row=SimpleNamespace(source='base',catalog_key='lamp',name='Лампа')
    assert matches(row,{106:product}) is None
    row.source='carpot.catalogue.v1'
    row.catalog_key='car:107556:product:999'
    assert matches(row,{106:product}) is None
    row.catalog_key='car:107555:product:106'
    assert matches(row,{106:product})==product


def test_pinned_batch_validates_product_and_snapshot_identity(monkeypatch):
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_URL','https://catalogue.example.test')
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_HOST','catalogue.example.test')
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_KEY','fixture')
    def transport(request):
        assert request.url.params.get_list('product_id')==['106','107']
        return httpx.Response(200,json={'car_id':107555,'snapshot_sha':'a'*64,'items':{'106':[],'107':[]}})
    adapter=CatalogueAdapter(transport=httpx.MockTransport(transport))
    assert adapter.article_batch(107555,[106,107],'a'*64)=={106:[],107:[]}
    with pytest.raises(CatalogueUnavailable):
        adapter.article_batch(107555,[106,107],'b'*64)


def test_auto_oem_xc60_directory_matches_missing_generation_with_available_facts():
    """A missing generation or engine can be assumed; a known conflicting generation cannot."""
    from types import SimpleNamespace
    from app.services.auto_oem import SourceCache
    v=SimpleNamespace(manufacturer='Volvo',model='XC60',generation='',engine_code='B4204T',
        year=2022,fuel_type='petrol',drive_type='AWD',engine_variant='',engine_displacement_l=2.0)
    entry=dict(manufacturer='Volvo',model='XC60 II',source_modification_id=126480,
        model_id=37773,manufacturer_id=120,snapshot_sha='a'*64,
        modification={'description':'2.0 T5 AWD'},specifications=[
            {'attributetype':'EngineCode','displayvalue':'B4204T'},
            {'attributetype':'ConstructionInterval','displayvalue':'03.2017 -'},
            {'attributetype':'FuelType','displayvalue':'petrol'},
            {'attributetype':'DriveType','displayvalue':'AWD'},
            {'attributetype':'Capacity','displayvalue':'2.0 l'}])
    cache=SourceCache();cache.directory=[entry]
    assert cache.resolve_directory(v)==(126480,37773,120,'a'*64,True)
    v.engine_code=''
    assert cache.resolve_directory(v)==(126480,37773,120,'a'*64,True)
    v.engine_code='B4204T';v.generation='I'
    assert cache.resolve_directory(v) is None
    v.generation='2'
    assert cache.resolve_directory(v)==(126480,37773,120,'a'*64,True)
    v.generation='II (2017)'
    assert cache.resolve_directory(v)==(126480,37773,120,'a'*64,True)
    v.generation='';cache.directory.insert(0,{**entry,'source_modification_id':126481})
    assert cache.resolve_directory(v)==(126480,37773,120,'a'*64,True)


def test_xc60_confirmed_modification_builds_plan_and_oem_without_vin_guess(logged, monkeypatch):
    """The six imported XC60 variants are usable after exact source confirmation."""
    from app.services import unified_catalogue as catalogue
    from app.services.auto_oem import enrich_vehicle

    response=logged.post('/api/v1/vehicles',json={
        'manufacturer':'Volvo','model':'XC60','year':2022,
        'vin':'YV4L12RK6N1970668',
    })
    assert response.status_code==201,response.text
    vid=response.json()['id']
    with Session(engine()) as db:
        v=db.get(Vehicle,vid)
        aid=v.account_id
        v.dismantling_v3={'global_selection':dict(
            car_id=126480,model_id=37773,manufacturer_id=120,
            source_snapshot_sha='a'*64,vehicle_basis=catalogue.vehicle_basis(v))}
        db.commit()

    source=envelope(126480)
    source['payload']['model_id']=37773
    source['payload']['source_snapshot_sha']='a'*64
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car,**kw:source)
    monkeypatch.setattr(CatalogueAdapter,'articles',lambda *a,**kw:detail_items())
    assert enrich_vehicle(engine(),aid,vid)==1
    assert enrich_vehicle(engine(),aid,vid)==0
    with Session(engine()) as db:
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==vid)))
        assert len(rows)==1
        assert rows[0].catalog_key=='car:126480:product:106'
        ref=db.get(Vehicle,vid).dismantling_v3['volvo_oem_references'][rows[0].id]
        assert ref['source_modification_id']==126480
        assert ref['oem_number']=='OEM-ONE'
        assert not ref['vin_verified']
        assert db.scalar(select(func.count()).select_from(Part).where(Part.vehicle_id==vid))==0


def test_pinned_batch_works_for_an_existing_volvo_snapshot():
    from app.services.auto_oem import SourceCache

    class Adapter:
        def article_batch(self, car_id, product_ids, snapshot_sha):
            assert (car_id,product_ids,snapshot_sha)==(107555,[106],'a'*64)
            return {106:detail_items()}

    payload=envelope()['payload']
    product=payload['categories'][0]
    assert SourceCache(Adapter()).get_offer_batch(payload,{106:product})[106][0]['oem_numbers']==['OEM-ONE','OEM-TWO']


def test_selection_switch_refreshes_automatic_oem_and_keeps_manual_history(logged, monkeypatch):
    from uuid import uuid4
    from app.services.auto_oem import enrich_vehicle

    response=logged.post('/api/v1/vehicles',json={
        'manufacturer':'Volvo','model':'XC60','year':2022,'vin':'YV4L12RK6N1970668',
    })
    assert response.status_code==201,response.text
    vehicle=response.json()
    url=f"/api/v1/vehicles/{vehicle['id']}"
    with Session(engine()) as db:
        account=db.get(Vehicle,vehicle['id']).account_id

    entries=[dict(source_modification_id=cid,model_id=13084,manufacturer_id=120,
                  manufacturer='Volvo',model='XC60 II',snapshot_sha=str(index)*64,
                  modification={'description':f'Variant {index}','constructioninterval':'2017 - 2025'})
             for index,cid in enumerate((126480,126481),1)]
    def directory(self,after=0,car_id=None,**kwargs):
        return {'items':[item for item in reversed(entries) if car_id is None or item['source_modification_id']==car_id]}
    def plan(self,car,**kwargs):
        result=envelope(car)
        result['payload']['source_snapshot_sha']=next(item['snapshot_sha'] for item in entries if item['source_modification_id']==car)
        return result
    def articles(self,car,product,sha,**kwargs):
        items=detail_items()
        items[0]['oem']=[{'manufacturerId':120,'OENbr':f'FIXTURE-{car}'}]
        return items
    monkeypatch.setattr(CatalogueAdapter,'directory',directory)
    monkeypatch.setattr(CatalogueAdapter,'plan',plan)
    monkeypatch.setattr(CatalogueAdapter,'articles',articles)

    assert enrich_vehicle(engine(),account,vehicle['id'])==1
    state=logged.get(url+'/global-dismantling').json()
    assert state['selection']['confirmation']=='auto_assumed'
    assert state['selection']['car_id']==126480
    assert state['oems']['106']['oem_number']=='FIXTURE-126480'
    row_key=state['keys']['106']
    result=logged.post(url+'/unified-catalogue/stock',json={'keys':[row_key],'confirm_physical_receipt':True})
    assert result.status_code==200,result.text
    with Session(engine()) as db:
        part=db.scalar(select(Part))
        part_id=part.id
        assert part.oem_provenance['modification_selection']=='auto_assumed'

    def switch(entry):
        result=logged.post(url+'/catalogue-selection',json={
            'request_key':str(uuid4()),'expected_basis':state['selection_basis'],
            **{key:entry[key] for key in ('source_modification_id','model_id','manufacturer_id')},
            'source_snapshot_sha':entry['snapshot_sha'],
        })
        assert result.status_code==200,result.text
        enrich_vehicle(engine(),account,vehicle['id'])

    switch(entries[1])
    with Session(engine()) as db:
        part=db.get(Part,part_id)
        assert part.oem_number=='FIXTURE-126481'
        assert part.quantity==1
        assert db.scalar(select(func.count()).select_from(DismantlingItem))==1
        changes=list(db.scalars(select(Operation).where(Operation.part_id==part_id,Operation.type=='part_update')))
        assert any(op.before.get('oem_number')=='FIXTURE-126480' for op in changes)
    result=logged.patch('/api/v1/parts/'+part_id+'/characteristics',json={
        'expected':{'oem_number':'FIXTURE-126481'},'values':{'oem_number':'MANUAL'},
    })
    assert result.status_code==200,result.text
    switch(entries[0])
    with Session(engine()) as db:
        assert db.get(Part,part_id).oem_number=='MANUAL'


def test_sibling_oem_candidates_are_visible_but_never_copied_to_stock(logged,monkeypatch):
    from app.services.auto_oem import enrich_vehicle
    response=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC60','year':2022})
    assert response.status_code==201,response.text
    vehicle_id=response.json()['id']
    url=f'/api/v1/vehicles/{vehicle_id}'
    with Session(engine()) as db:
        account=db.get(Vehicle,vehicle_id).account_id
    entries=[dict(source_modification_id=car,model_id=13084,manufacturer_id=120,manufacturer='Volvo',
                  model='XC60',snapshot_sha='a'*64,modification={'constructioninterval':'2017 - 2025'})
             for car in (126480,126481)]
    def batch(self,car,ids,sha):
        items=detail_items()
        items[0]['oem']=[] if car==126480 else [{'manufacturerId':120,'OENbr':'OTHER-MODIFICATION'}]
        return {106:items}
    monkeypatch.setattr(CatalogueAdapter,'directory',lambda *args,**kwargs:{'items':entries})
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car,**kwargs:envelope(car))
    monkeypatch.setattr(CatalogueAdapter,'article_batch',batch)
    assert enrich_vehicle(engine(),account,vehicle_id)==0
    state=logged.get(url+'/global-dismantling').json()
    assert state['oems']=={}
    candidates=state['unconfirmed_oem_candidates']['106']
    assert [(item['oem_number'],item['source_modification_id'],item['status']) for item in candidates]==[
        ('OTHER-MODIFICATION',126481,'unconfirmed'),
    ]
    r=logged.post(url+'/unified-catalogue/stock',json={
        'keys':[state['keys']['106']],'confirm_physical_receipt':True,
    })
    assert r.status_code==200,r.text
    with Session(engine()) as db:
        assert db.scalar(select(Part)).oem_number==''


def test_canonical_prd_backfill_requires_catalogue_checksum():
    from types import SimpleNamespace
    from app.services.auto_oem import matches

    row=SimpleNamespace(source='carpot.v3',catalog_key='generated-item',name='Legacy',
                        category_name='Existing',subcategory_name='Existing',
                        plan_v3={'canonical_part_type_id':'fixture-type'})
    product={'product_id':106,'kind':'review','source_fitment_linked':True,'source_prd_sha256':'a'*64}
    assert matches(row,{106:product},{'fixture-type':{(106,'b'*64)}}) is None
    assert matches(row,{106:product},{'fixture-type':{(106,'a'*64)}})==product


def test_auto_oem_account_row_lock_is_shared_on_postgresql():
    """Avoid the PostgreSQL trap: key_share=True alone emits NO KEY UPDATE."""
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql
    from app.models import Account
    sql=str(select(Account).with_for_update(read=True,key_share=True).compile(
        dialect=postgresql.dialect()))
    assert sql.endswith('FOR KEY SHARE') and 'FOR NO KEY UPDATE' not in sql

def test_auto_oem_directory_fallback_requires_exact_model_year_not_brand_only():
    from types import SimpleNamespace
    from app.services.auto_oem import SourceCache
    item=dict(manufacturer='Volvo',model='XC60 II',source_modification_id=126478,
        model_id=37773,manufacturer_id=120,snapshot_sha='a'*64,
        modification={'description':'2.0 D4 AWD','constructioninterval':'03.2017 -'},
        specifications=[{'attributetype':'FuelType','displayvalue':'diesel'}])
    v=SimpleNamespace(manufacturer='Volvo',model='XC60',generation='',
        year=2022,engine_code='',fuel_type='petrol',drive_type='',engine_variant='',
        engine_displacement_l=None)
    cache=SourceCache();cache.directory=[item]
    assert cache.resolve_directory(v)==(126478,37773,120,'a'*64,True)
    v.model='XC90'
    assert cache.resolve_directory(v) is None
    v.model='XC60';v.year=2010
    assert cache.resolve_directory(v) is None
    v.year=2022;v.generation='I'
    assert cache.resolve_directory(v) is None
