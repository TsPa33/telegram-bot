"""Actual prices, existing ledger, compare-and-set notes, no staging calls."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import engine
from app.models import StockRequest, Operation
from conftest import signup
from test_orders import buyer, stocked, line, create, action


def key():return str(uuid4())
def sale(c,p,**kw):return c.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'sale','quantity':1,'request_key':key(),'sale_price':'12.34','sale_currency':'USD',**kw})


def test_price_snapshot_and_sequence(logged,vehicle):
    p=stocked(logged,vehicle,quantity=3)
    assert sale(logged,p).status_code==200
    assert sale(logged,p,sale_price='0.01',sale_currency='UAH').status_code==200
    logged.patch('/api/v1/parts/'+p['id']+'/price',json={'selling_price':'999.98','currency':'UAH'})
    rows=logged.get('/api/v1/sales').json()['items']
    assert {r['unit_price'] for r in rows}=={'12.34','0.01'}
    assert {r['currency'] for r in rows}=={'UAH','USD'}
    assert all(r['quantity']==1 and r['source']=='quick' and r['actor_name']=='Власник' for r in rows)
    assert rows[0]['donor']['model']==vehicle['model']
    assert sale(logged,p).json()['quantity']==0
    assert sale(logged,p).status_code==409
    assert logged.get('/api/v1/parts/'+p['id']).json()['archived'] is False
    for body in ({'sale_price':'1.001'},{'sale_currency':'EUR'},{'sale_currency':None},{'type':'receipt'}):
        assert sale(logged,p,**body).status_code==422


def test_concurrent_price_replay_and_legacy_fingerprint(logged,vehicle):
    p=stocked(logged,vehicle,quantity=2);request=key()
    def send(_):
        with TestClient(app) as c:
            c.cookies.update(dict(logged.cookies));c.headers.update(dict(logged.headers))
            return sale(c,p,request_key=request)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,range(2)))
    assert all(r.status_code==200 and r.json()['quantity']==1 for r in results)
    assert logged.get('/api/v1/sales').json()['total']==1
    assert sale(logged,p,request_key=request,sale_price='0.02').status_code==409
    # Legacy payload remains legal; missing actual price stays unknown.
    legacy={'type':'sale','quantity':1,'request_key':key()}
    assert logged.post('/api/v1/parts/'+p['id']+'/operations',json=legacy).status_code==200
    assert logged.post('/api/v1/parts/'+p['id']+'/operations',json=legacy).status_code==200
    row=logged.get('/api/v1/sales').json()['items'][0]
    assert row['unit_price'] is None and row['price_recorded'] is False


def test_notes_conflict_and_inspection_preserve_stock(logged,vehicle):
    p=stocked(logged,vehicle);url='/api/v1/parts/'+p['id']
    assert logged.patch(url+'/notes',json={'internal_notes':'Подряпина','expected_notes':''}).status_code==200
    assert logged.patch(url+'/notes',json={'internal_notes':'Чужа зміна','expected_notes':''}).status_code==409
    assert logged.get(url).json()['internal_notes']=='Подряпина'
    row=logged.patch(url+'/inspection',json={'condition':'damaged','availability':'unchecked'}).json()
    assert row['quantity']==3 and row['reserved_quantity']==0
    assert sale(logged,p).status_code==200
    assert logged.get('/api/v1/audit',params={'part_id':p['id'],'type':'part_update'}).json()['total']==2
    assert logged.patch(url+'/notes',json={'internal_notes':'  Зберегти пробіли  ','expected_notes':'Подряпина'}).json()['internal_notes']=='  Зберегти пробіли  '
    assert logged.patch(url+'/notes',json={'internal_notes':'Оновлено','expected_notes':'  Зберегти пробіли  '}).status_code==200


def test_orders_share_projection_and_reserved_stock(logged,vehicle,monkeypatch):
    p=stocked(logged,vehicle,quantity=2);b=buyer(logged)
    order=create(logged,b,[line(p,2,unit_price='4.56',currency='USD')])
    assert action(logged,order,'reserve').status_code==200
    assert sale(logged,p).status_code==409
    assert logged.get('/api/v1/sales').json()['total']==0
    assert action(logged,order,'sell').status_code==200
    assert action(logged,order,'sell').status_code==409
    rows=logged.get('/api/v1/sales',params={'source':'order'}).json()['items']
    assert len(rows)==1 and rows[0]['unit_price']=='4.56' and rows[0]['total']=='9.12'
    assert rows[0]['buyer_name']=='Покупець' and rows[0]['quantity']==2
    # Historical operation inserted without sale metadata by the old StockInput.
    from app.schemas import StockInput
    import app.services.orders as service
    monkeypatch.setattr(service,'StockInput',lambda **kw:StockInput(**{k:v for k,v in kw.items() if k not in ('sale_price','sale_currency')}))
    oldpart=stocked(logged,vehicle);oldorder=create(logged,b,[line(oldpart)])
    assert action(logged,oldorder,'sell').status_code==200
    assert logged.get('/api/v1/sales').json()['items'][0]['unit_price']=='123.45'
    assert logged.get('/api/v1/sales',params={'source':'quick'}).json()['total']==0
    assert logged.get('/api/v1/parts/'+p['id']).json()['quantity']==0


def test_sales_filters_auth_and_tenant(logged,vehicle):
    p=stocked(logged,vehicle,article_number='ABC-56');sale(logged,p)
    assert logged.get('/api/v1/sales',params={'q':'abc-56','vehicle_id':vehicle['id']}).json()['total']==1
    assert logged.get('/api/v1/sales',params={'q':'ка'}).json()['total']==1
    assert logged.get('/api/v1/sales',params={'date_from':'2020-01-01T00:00:00','date_to':'2099-01-01T00:00:00Z'}).status_code==200
    assert logged.get('/api/v1/sales',params={'q':'missing'}).json()['total']==0
    assert logged.get('/api/v1/sales',params={'date_from':'2099-01-01T00:00:00Z'}).json()['total']==0
    assert logged.get('/api/v1/sales',params={'limit':1,'offset':1}).json()['items']==[]
    assert logged.get('/api/v1/sales-workspace/readiness').json()['contract_version']==5
    assert logged.get('/api/v1/orders/readiness').json()['contract_version']==6
    assert logged.get('/api/v1/workshop/readiness').json()['contract_version']==7
    with TestClient(app) as other:
        assert other.get('/api/v1/sales').status_code==401
        signup(other,'other-workshop@example.test')
        assert other.get('/api/v1/sales').json()['total']==0
        assert other.patch('/api/v1/parts/'+p['id']+'/notes',json={'internal_notes':'x','expected_notes':''}).status_code==404
    csrf=logged.headers.pop('X-CSRF-Token')
    assert sale(logged,p).status_code==403
    logged.headers['X-CSRF-Token']=csrf


def test_legacy_hash_compatibility_and_financial_key_required(logged,vehicle):
    import hashlib,json
    p=stocked(logged,vehicle)
    request=key();body={'type':'sale','quantity':1,'request_key':request}
    assert logged.post('/api/v1/parts/'+p['id']+'/operations',json=body).status_code==200
    old_payload={'part_id':p['id'],'type':'sale','quantity':1,'location':None,'reason':'Продаж'}
    old_hash=hashlib.sha256(json.dumps(old_payload,sort_keys=True).encode()).hexdigest()
    with engine().connect() as db:
        assert db.execute(select(StockRequest.fingerprint).where(StockRequest.request_key==request)).scalar_one()==old_hash
    assert sale(logged,p,request_key=None).status_code==422
    # Existing append-only audit trigger also protects financial snapshots.
    assert sale(logged,p).status_code==200
    import pytest
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy import text
    with pytest.raises(DBAPIError):
        with engine().begin() as db:db.execute(text("UPDATE operations SET reason='tamper' WHERE type='sale'"))
