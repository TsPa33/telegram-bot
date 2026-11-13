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
    from app.services.catalogue_format import digest
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
    assert row['reference']['oem_number']=='OEM-ONE' and row['stock_eligible']
    with Session(engine()) as db:
        p=db.get(Part,row['part_id']);p.selling_price=123.45;p.article_number='MANUAL';db.commit()
        before=snapshot(p)
    assert logged.post(url,json=body(data,row,assign_stock=True)).status_code==422
    request=body(data,row,assign_stock=True,confirm_physical_oem=True)
    result=logged.post(url,json=request)
    assert result.status_code==200,result.text
    assert result.json()['stock_assigned']
    tree=logged.get(base+'/assemblies').json()
    assert next(x for x in tree['items'] if x['id']==row['id'])['stock_oem']=='OEM-ONE'
    assert logged.post(url,json=request).json()==result.json()
    with Session(engine()) as db:
        p=db.get(Part,row['part_id']);after=snapshot(p)
        assert p.oem_number=='OEM-ONE' and p.oem_provenance['vin_verified'] is False
        assert {k:v for k,v in before.items() if k not in ('oem_number','oem_provenance')}=={k:v for k,v in after.items() if k not in ('oem_number','oem_provenance')}
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1
    data=preview();row=next(x for x in data['plan_items'] if x['id']==row['id'])
    assert not row['stock_eligible']
    assert logged.post(url,json=body(data,row,assign_stock=True,confirm_physical_oem=True)).status_code==409
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


def test_volvo_auto_fills_missing_once_and_preserves_plan(logged,volvo,monkeypatch):
    from uuid import uuid4
    from app.services.inventory import snapshot
    base=f"/api/v1/vehicles/{volvo['id']}"
    assert logged.post(base+'/unified-catalogue/base').status_code==200
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda self,car:envelope(car,'partial'))
    with Session(engine()) as db:
        rows=list(db.scalars(select(DismantlingItem).order_by(DismantlingItem.id)))
        assert len(rows)>2
        rows[0].name='Лампа';rows[0].included=True
        rows[1].name='Лампа';rows[1].included=False
        db.commit()
        target=rows[0].id; excluded=rows[1].id
        before=[snapshot(x) for x in rows]
    preview=logged.get(base+'/volvo-oem-preview',params={'source_modification_id':107555}).json()
    request=dict(request_key=str(uuid4()),source_modification_id=107555,
        snapshot_sha=preview['snapshot_sha'],expected_vehicle_basis=preview['vehicle_basis'],confirm_modification=True)
    url=base+'/volvo-oem-auto'
    assert logged.post(url,json={**request,'confirm_modification':False}).status_code==422
    assert logged.post(url,json={**request,'snapshot_sha':'b'*64}).status_code==409
    response=logged.post(url,json=request)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['added']>=1 and result['stock_changed'] is False
    assert next(x for x in result['items'] if x['item_id']==target)['oem_number']=='OEM-ONE'
    assert result['skipped'][excluded]=='not_eligible'
    assert logged.post(url,json=request).json()==result
    assert logged.post(url,json={**request,'request_key':str(uuid4())}).json()['added']==0
    after=logged.get(base+'/volvo-oem-preview',params={'source_modification_id':107555}).json()
    ref=next(x for x in after['plan_items'] if x['id']==target)['reference']
    assert ref['status']=='auto_selected_cross_reference' and ref['vin_verified'] is False
    assert ref['alternative_count']==2
    with Session(engine()) as db:
        assert [snapshot(x) for x in db.scalars(select(DismantlingItem).order_by(DismantlingItem.id))]==before
        assert db.scalar(select(func.count()).select_from(Part))==0
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==0
