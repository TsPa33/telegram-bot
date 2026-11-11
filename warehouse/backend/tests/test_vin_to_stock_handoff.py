"""VIN→existing donor→exact fixture catalogue→existing bulk ledger. LOCAL TEST DATA ONLY."""
from copy import deepcopy
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Vehicle,Part,DismantlingItem,Operation
from app.services import unified_catalogue as catalogue,vin_lookup
from tests.test_unified_catalogue import envelope


def setup_source(monkeypatch,car=107555,maker='Volvo',mid=120):
    data=envelope(car=car,coverage='partial')['payload']
    data.update(schema='carpot.vehicle.plan.v1',manufacturer_id=mid)
    entry=dict(source_modification_id=car,manufacturer_id=mid,manufacturer=maker,model_id=data['model_id'],model='Synthetic source model',generation=None,snapshot_sha=data['source_snapshot_sha'],modification=data['modification'],type_count=1,article_count=1,oem_links=0,coverage='partial')
    monkeypatch.setattr(catalogue.CatalogueAdapter,'directory',lambda *a,**k:dict(items=[entry],next_after=None))
    monkeypatch.setattr(catalogue.CatalogueAdapter,'plan',lambda *a,**k:dict(payload=deepcopy(data)))
    return entry


def binding(c,v,entry):
    state=c.get(f"/api/v1/vehicles/{v['id']}/global-dismantling").json()
    return dict(request_key=str(uuid4()),source_modification_id=entry['source_modification_id'],model_id=entry['model_id'],manufacturer_id=entry['manufacturer_id'],source_snapshot_sha=entry['snapshot_sha'],expected_basis=state['selection_basis'],confirm_exact_modification=True)


def bulk(c,v,ids,action,**extra):
    path=f"/api/v1/vehicles/{v['id']}/dismantling-v3"
    p=c.post(path+'/bulk/preview',json=dict(ids=ids,action=action));assert p.status_code==200,p.text
    body=dict(ids=ids,action=action,request_key=str(uuid4()),etag=p.json()['etag'],confirm=True,**extra)
    if action=='receipt':body['preview_token']=p.json()['preview_token']
    r=c.post(path+'/bulk',json=body);assert r.status_code==200,r.text
    return r,body


@pytest.mark.parametrize('vin,maker,car,mid',[
 ('YV4L12RK6N1970668','Volvo',111111,120),
 ('YV4A22PK2G1092943','Volvo',107555,120),
 ('VF1AAAAA000000001','Renault',222222,93)])
def test_vin_same_donor_exact_selection_bulk_receipt_replay(logged,monkeypatch,vin,maker,car,mid):
    entry=setup_source(monkeypatch,car,maker,mid)
    monkeypatch.setattr(vin_lookup,'lookup',lambda vin:dict(vin=vin,source='offline synthetic fixture',vehicle=dict(manufacturer=maker,model='Synthetic VIN model',year=2020),additional={},field_sources={}))
    decoded=logged.get('/api/v1/vehicles/vin/decode',params={'vin':vin});assert decoded.status_code==200
    body={**decoded.json()['vehicle'],'vin':vin,'vin_details':dict(source='offline synthetic fixture',characteristics=decoded.json()['vehicle'])}
    r=logged.post('/api/v1/vehicles',json=body);assert r.status_code==201,r.text
    v=r.json();assert logged.post('/api/v1/vehicles',json=body).status_code==409
    data=binding(logged,v,entry);url=f"/api/v1/vehicles/{v['id']}/catalogue-selection"
    r=logged.post(url,json=data);assert r.status_code==200,r.text
    assert logged.post(url,json=data).json()==r.json()
    fresh=logged.get('/api/v1/vehicles/'+v['id']).json()
    assert fresh['vin']==vin and fresh['vin_details']['characteristics']==body['vin_details']['characteristics']
    path=f"/api/v1/vehicles/{v['id']}/dismantling-v3"
    p=logged.post(path+'/preview',json=dict(facts=[],universal=True));assert p.status_code==200,p.text
    assert p.json()['catalogue_status']['generator']['exact_source_positions']==1
    save=dict(facts=[],universal=True,token=p.json()['token'],request_key=str(uuid4()),confirm=True)
    r=logged.post(path+'/save',json=save);assert r.status_code==200,r.text
    ids=logged.get(path).json()['items'];assert len(ids)==1
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Vehicle))==1
        assert db.scalar(select(func.count()).select_from(Part))==0
    ids=[row['id'] for row in ids]
    bulk(logged,v,ids,'present');bulk(logged,v,ids,'dismantled')
    r,receipt=bulk(logged,v,ids,'receipt',lines=[dict(id=ids[0],quantity=1,location='SYNTHETIC-A1')])
    assert logged.post(path+'/bulk',json=receipt).json()==r.json()
    assert logged.post(path+'/bulk',json={**receipt,'request_key':str(uuid4())}).status_code==409
    # A fresh explicit attempt skips previously received rows, even with a fresh key.
    second,_=bulk(logged,v,ids,'receipt',lines=[]);assert second.json()['updated']==0
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==1
        part=db.scalar(select(Part));assert part.quantity==1 and part.location=='SYNTHETIC-A1'
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==0
        assert db.scalar(select(func.count()).select_from(DismantlingItem))==1


def test_binding_guards_history_stale_source_and_workspace(logged,vehicle,monkeypatch):
    entry=setup_source(monkeypatch,maker=vehicle['manufacturer'])
    body=binding(logged,vehicle,entry);url=f"/api/v1/vehicles/{vehicle['id']}/catalogue-selection"
    assert logged.post(url,json={**body,'confirm_exact_modification':False}).status_code==422
    assert logged.post(url,json={**body,'source_snapshot_sha':'0'*64}).status_code==409
    assert logged.post(url,json={**body,'expected_basis':'0'*64}).status_code==409
    from conftest import signup
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as other:
        signup(other,'other-vin-stock@example.test')
        assert other.post(url,json=body).status_code==404
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);db.add(DismantlingItem(account_id=v.account_id,vehicle_id=v.id,source='manual',catalog_key='historical',name='Do not overwrite',category_key='old',category_name='Old',subcategory_key='old',subcategory_name='Old',plan_v3={'inspection':'present'}));db.commit()
    assert logged.post(url,json=body).status_code==409
    with Session(engine()) as db:
        assert db.scalar(select(DismantlingItem)).name=='Do not overwrite'
        assert not db.get(Vehicle,vehicle['id']).dismantling_v3.get('global_selection')


def test_binding_csrf_identity_fingerprint_and_source_outage(logged,vehicle,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    entry=setup_source(monkeypatch,maker=vehicle['manufacturer'])
    body=binding(logged,vehicle,entry);url=f"/api/v1/vehicles/{vehicle['id']}/catalogue-selection"
    with TestClient(app) as no_csrf:
        no_csrf.cookies.update(logged.cookies)
        assert no_csrf.post(url,json=body).status_code==403
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.vin_details={'characteristics':{'drive_type':'AWD'}};db.commit()
    assert logged.post(url,json=body).status_code==409
    body=binding(logged,vehicle,entry)
    def unavailable(*a,**k):raise catalogue.CatalogueUnavailable('offline source unavailable')
    monkeypatch.setattr(catalogue.CatalogueAdapter,'plan',unavailable)
    assert logged.post(url,json=body).status_code==503
    with Session(engine()) as db:
        assert not db.get(Vehicle,vehicle['id']).dismantling_v3.get('global_selection')
        assert db.scalar(select(func.count()).select_from(Part))==0


def test_binding_readonly_employee_cannot_write(logged,vehicle,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    from tests.test_team import employee,activate
    entry=setup_source(monkeypatch,maker=vehicle['manufacturer'])
    body=binding(logged,vehicle,entry)
    _,invite=employee(logged,permissions=['vehicles.view','catalog.view','inventory.view'])
    c=activate(invite)
    try:assert c.post(f"/api/v1/vehicles/{vehicle['id']}/catalogue-selection",json=body).status_code==403
    finally:c.close()


def test_present_only_then_receipt_in_two_atomic_batches_without_duplicate_stock(logged,vehicle):
    """Regression: 123 selected/confirmed, zero previously dismantled, 100+23 received.

    All data use the local synthetic generator and dedicated *_test PostgreSQL.
    No external VIN provider, Plan.Parts API or production stock.
    """
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3"
    p=logged.post(path+'/preview',json=dict(facts=[],universal=True))
    assert p.status_code==200,p.text
    saved=logged.post(path+'/save',json=dict(
        facts=[],universal=True,token=p.json()['token'],
        request_key=str(uuid4()),confirm=True))
    assert saved.status_code==200,saved.text
    items=logged.get(path).json()['items']
    ids=[r['id'] for r in items if r['selectable']][:123]
    assert len(ids)==123,"The synthetic fallback fixture must expose >100 distinct placements"

    bulk(logged,vehicle,ids,'present')
    pre=logged.post(path+'/bulk/preview',json=dict(ids=ids,action='receipt'))
    assert pre.status_code==200,pre.text
    assert pre.json()['confirmed']==123
    assert pre.json()['dismantled']==0
    assert len(pre.json()['eligible_ids'])==123

    # A receipt without the explicit physical confirmation is rejected without writes.
    rejected=logged.post(path+'/bulk',json=dict(
        ids=ids[:100],action='receipt',etag=pre.json()['etag'],
        preview_token=pre.json()['preview_token'],request_key=str(uuid4()),
        confirm=False,lines=[dict(id=id,quantity=1) for id in ids[:100]]))
    assert rejected.status_code==422
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==0

    first,original=bulk(logged,vehicle,ids[:100],'receipt',
        lines=[dict(id=id,quantity=1,location='SYNTHETIC-B1') for id in ids[:100]])
    assert first.json()['updated']==100
    # Retry the same key after the first transaction: replay, not a second receipt.
    replay=logged.post(path+'/bulk',json=original)
    assert replay.status_code==200,replay.text
    assert replay.json()==first.json()
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==100

    rest,_=bulk(logged,vehicle,ids[100:],'receipt',
        lines=[dict(id=id,quantity=1,location='SYNTHETIC-B2') for id in ids[100:]])
    assert rest.json()['updated']==23
    duplicate,_=bulk(logged,vehicle,ids,'receipt',lines=[])
    assert duplicate.json()['updated']==0
    assert duplicate.json()['skipped']==123

    with Session(engine()) as db:
        parts=list(db.scalars(select(Part)))
        assert len(parts)==123
        assert all(part.quantity==1 for part in parts)
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==123
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.id.in_(ids))))
        assert len(rows)==123
        assert all(row.status=='dismantled' and row.part_id and row.received_at for row in rows)
