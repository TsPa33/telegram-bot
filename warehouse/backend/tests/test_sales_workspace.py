"""Seller search/currency/replay contract. Disposable PostgreSQL, no providers."""
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
from uuid import uuid4
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from app.db import engine
from app.main import app
from app.models import Part
from conftest import signup


@pytest.fixture(autouse=True)
def currency_client(logged):
    logged.headers['X-Warehouse-Client']='5'


def create(c,v,name,**extra):
    r=c.post('/api/v1/parts',json={'name':name,'vehicle_id':v['id'],**extra});assert r.status_code==201,r.text
    p=r.json();r=c.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'receipt','quantity':3,'reason':'Test stock'});assert r.status_code==200
    return p


def test_search_partial_unicode_oem_article_vehicle_and_physical_only(logged):
    volvo=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2010}).json()
    bmw=logged.post('/api/v1/vehicles',json={'manufacturer':'BMW','model':'X3','year':2012}).json()
    create(logged,volvo,'Капот',oem_number='OEM-АК123',article_number='ABC-111')
    create(logged,volvo,'Кардан',article_number='DEF-222')
    create(logged,bmw,'Капот BMW')
    logged.post('/api/v1/parts',json={'name':'Капот потенційний','vehicle_id':volvo['id']})
    for term,count in [('ка',2),('КА',2),('КаПоТ',1),('oem-ак123',1),('abc-111',1),('absent test',0)]:
        r=logged.get('/api/v1/parts',params={'q':term,'manufacturer':'vOlVo','model':'xc90','in_stock':'true'})
        assert r.status_code==200 and r.json()['total']==count,r.text
    assert logged.get('/api/v1/parts',params={'q':'ка','in_stock':'true','vehicle_id':bmw['id']}).json()['total']==1
    assert logged.get('/api/v1/parts',params={'q':'%','in_stock':'true'}).json()['total']==0


def test_exact_price_currency_patch_old_client_guard_and_analytics(logged,vehicle):
    p=create(logged,vehicle,'Price test',selling_price='123.45',unit_cost='1.00')
    url='/api/v1/parts/'+p['id']
    assert p['currency']=='UAH'
    for amount,currency in [('123456789012.34','USD'),('0.01','UAH'),('45.67','USD')]:
        r=logged.patch(url+'/price',json={'selling_price':amount,'currency':currency})
        assert r.status_code==200,r.text
        assert r.json()['selling_price']==amount and r.json()['currency']==currency
        with engine().connect() as db:
            row=db.execute(select(Part.selling_price,Part.currency).where(Part.id==p['id'])).one()
            assert str(row[0])==amount and row[1]==currency
    # Price PATCH touches no stock or owner fields.
    row=logged.get(url).json();assert row['quantity']==3 and row['name']=='Price test'
    assert logged.put(url,json={'name':row['name'],'selling_price':'50.00'}).status_code==409
    # A legacy edit with unchanged price preserves USD, never relabels it UAH.
    assert logged.put(url,json={'name':'Legacy description edit','selling_price':'45.67'}).json()['currency']=='USD'
    for body in ({'selling_price':'1.001','currency':'UAH'},{'selling_price':'-1','currency':'USD'},{'selling_price':'1','currency':'EUR'}):
        assert logged.patch(url+'/price',json=body).status_code==422
    summary=logged.get('/api/v1/dashboard').json()
    assert float(summary['estimated_sales_value'])==0
    assert float(summary['potential_gross_margin'])==0
    assert next(r for r in summary['valuation_by_currency'] if r['currency']=='USD')['value'] in ('137.01',137.01)
    logged.headers.pop('X-Warehouse-Client')
    assert logged.get(url).json()['selling_price'] is None
    assert logged.get(url).json()['price_requires_currency_client'] is True
    assert logged.get('/api/v1/parts').json()['items'][0]['selling_price'] is None
    logged.headers['X-Warehouse-Client']='5'
    assert logged.get(url).json()['selling_price']=='45.67'
    assert logged.patch(url+'/price',json={'selling_price':None,'currency':'USD'}).json()['selling_price'] is None


def test_parallel_sale_replay_and_payload_conflict(logged,vehicle):
    p=create(logged,vehicle,'Replay part',selling_price='10.00')
    body={'type':'sale','quantity':1,'request_key':str(uuid4())};url='/api/v1/parts/'+p['id']+'/operations'
    def send(_):
        with TestClient(app) as c:
            c.cookies.update(dict(logged.cookies));c.headers.update(dict(logged.headers))
            r=c.post(url,json=body);assert r.status_code==200,r.text;return r.json()
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(send,range(2)))
    assert responses[0]==responses[1] and responses[0]['quantity']==2
    assert logged.post(url,json=body).json()['quantity']==2
    assert logged.post(url,json={**body,'quantity':2}).status_code==409
    assert logged.get('/api/v1/parts/'+p['id']).json()['quantity']==2
    audit=logged.get('/api/v1/audit',params={'part_id':p['id'],'type':'sale'}).json()
    assert audit['total']==1 and audit['items'][0]['reason']=='Продаж'
    # A genuinely new sale gets a new key. Optional short note is allowed.
    assert logged.post(url,json={**body,'request_key':str(uuid4()),'reason':'ok'}).json()['quantity']==1


def test_transfer_writeoff_reserve_keep_ledger_and_replay(logged,vehicle):
    p=create(logged,vehicle,'Operations part');url='/api/v1/parts/'+p['id']+'/operations'
    def op(type,**extra):return logged.post(url,json={'type':type,'request_key':str(uuid4()),**extra})
    assert op('write_off',quantity=1).status_code==422
    assert op('transfer',location='A-02',reason='Moved test').json()['quantity']==3
    assert op('reserve',quantity=2,reason='Reserve test').json()['available_quantity']==1
    assert op('sale',quantity=2).status_code==409
    assert op('write_off',quantity=1,reason='Пошкодження').json()['quantity']==2
    assert op('release',quantity=2,reason='Release test').json()['available_quantity']==2
    r=op('sale',quantity=2);assert r.json()['quantity']==0 and r.json()['availability']=='absent'
    assert logged.get('/api/v1/parts',params={'in_stock':'true'}).json()['total']==0
    kinds={r['type'] for r in logged.get('/api/v1/audit',params={'part_id':p['id']}).json()['items']}
    assert {'sale','write_off','transfer','reserve','release'}<=kinds


def test_price_operations_auth_csrf_isolation(logged,vehicle):
    p=create(logged,vehicle,'Owned');url='/api/v1/parts/'+p['id']
    with TestClient(app) as c:
        assert c.patch(url+'/price',json={'selling_price':'1','currency':'USD'}).status_code==401
        signup(c,'other-seller@example.test')
        assert c.patch(url+'/price',json={'selling_price':'1','currency':'USD'}).status_code==404
        assert c.post(url+'/operations',json={'type':'sale','quantity':1,'request_key':str(uuid4())}).status_code==404
        assert c.get('/api/v1/parts',params={'q':'Owned','in_stock':'true'}).json()['total']==0
    logged.headers.pop('X-CSRF-Token')
    assert logged.patch(url+'/price',json={'selling_price':'1','currency':'USD'}).status_code==403
    assert logged.post(url+'/operations',json={'type':'sale','quantity':1}).status_code==403


def test_currency_migration_preserves_old_price_and_protects_usd(logged,vehicle):
    p=create(logged,vehicle,'Migration part',selling_price='123.45')
    with engine().connect() as db:
        before=db.execute(text('SELECT before, after FROM operations ORDER BY id')).all()
    run([sys.executable,'-m','alembic','downgrade','e17b6c04a932'],check=True)
    run([sys.executable,'-m','alembic','upgrade','head'],check=True)
    assert logged.get('/api/v1/parts/'+p['id']).json()['selling_price']=='123.45'
    assert logged.get('/api/v1/parts/'+p['id']).json()['currency']=='UAH'
    with engine().connect() as db:assert db.execute(text('SELECT before, after FROM operations ORDER BY id')).all()==before
    logged.patch('/api/v1/parts/'+p['id']+'/price',json={'selling_price':'123.45','currency':'USD'})
    result=run([sys.executable,'-m','alembic','downgrade','e17b6c04a932'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Cannot discard' in result.stderr
    assert logged.get('/api/v1/sales-workspace/readiness').json()['contract_version']==5


def test_sales_readiness_rejects_missing_guard_table(logged):
    with engine().begin() as db:db.execute(text('ALTER TABLE stock_requests RENAME TO stock_requests_offline'))
    try:assert logged.get('/api/v1/sales-workspace/readiness').status_code==503
    finally:
        with engine().begin() as db:db.execute(text('ALTER TABLE stock_requests_offline RENAME TO stock_requests'))
