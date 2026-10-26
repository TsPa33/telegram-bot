"""Real PostgreSQL + actual sale/order APIs. No mocked aggregation responses."""
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from test_orders import stocked,buyer,line,create,action
from test_workshop import sale
from test_team import employee,activate
from conftest import signup


def result(c,**params):
    r=c.get('/api/v1/sales/summary',params={'date_from':'2026-01-01','date_to':'2026-12-31',**params})
    assert r.status_code==200,r.text
    return r.json()


@pytest.fixture
def sale_date(monkeypatch):
    import app.services.inventory as inv
    original=inv.record
    current=['2026-06-15T12:00:00+00:00']
    def record(*args,**kwargs):
        operation=original(*args,**kwargs)
        if operation.type=='sale':operation.created_at=datetime.fromisoformat(current[0])
        return operation
    monkeypatch.setattr(inv,'record',record)
    return lambda value:current.__setitem__(0,value)


def test_actual_sales_replay_mixed_currency_unknown_price_and_current_prices(logged,vehicle,sale_date):
    p=stocked(logged,vehicle,quantity=5)
    key=str(uuid4())
    for _ in range(2):assert sale(logged,p,request_key=key,quantity=2,sale_price='0.03',sale_currency='USD').status_code==200
    assert sale(logged,p,sale_price='12.34',sale_currency='UAH').status_code==200
    assert logged.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'sale','quantity':1,'request_key':str(uuid4())}).status_code==200
    assert logged.patch('/api/v1/parts/'+p['id']+'/price',json={'selling_price':'99999','currency':'USD'}).status_code==200
    d=result(logged,date_from='2026-06-14',date_to='2026-06-16')
    assert d['sales_count']==3 and d['units']==4 and d['unpriced_units']==1
    assert d['totals_by_currency']==[{'currency':'UAH','amount':'12.34','units':1,'sales_count':1},{'currency':'USD','amount':'0.06','units':2,'sales_count':1}]
    assert [p['units'] for p in d['periods']]==[0,4,0]
    assert d['returns_supported'] is False and d['date_semantics']=='operation_created_at'
    assert sum(Decimal(r['total']) for r in logged.get('/api/v1/sales').json()['items'] if r['currency']=='USD')==Decimal('0.06')


def test_order_reserved_cancelled_unsold_and_legacy_snapshot(logged,vehicle,sale_date,monkeypatch):
    p=stocked(logged,vehicle,quantity=6);b=buyer(logged)
    order=create(logged,b,[line(p,2,unit_price='4.56',currency='USD')])
    assert action(logged,order,'reserve').status_code==200
    assert result(logged)['sales_count']==0
    key={'request_key':str(uuid4())}
    for _ in range(2):assert action(logged,order,'sell',key).status_code==200
    assert action(logged,order,'cancel').status_code==409
    cancelled=create(logged,b,[line(p)])
    assert action(logged,cancelled,'reserve').status_code==200
    assert action(logged,cancelled,'cancel').status_code==200
    create(logged,b,[line(p)]) # unsold order contributes nothing
    from app.schemas import StockInput
    import app.services.orders as service
    monkeypatch.setattr(service,'StockInput',lambda **kw:StockInput(**{k:v for k,v in kw.items() if k not in ('sale_price','sale_currency')}))
    legacy=create(logged,b,[line(p,unit_price='0.02',currency='UAH')])
    assert action(logged,legacy,'sell').status_code==200
    d=result(logged)
    assert d['units']==3 and d['sales_count']==2 and d['unpriced_units']==0
    assert {v['currency']:v['amount'] for v in d['totals_by_currency']}=={'USD':'9.12','UAH':'0.02'}
    assert logged.get('/api/v1/parts/'+p['id']).json()['quantity']==3


@pytest.mark.parametrize('interval,dates',[('day',['2026-01-31','2026-02-01','2026-02-02']),('week',['2026-01-26','2026-02-02']),('month',['2026-01-01','2026-02-01'])])
def test_empty_and_partial_periods(logged,vehicle,sale_date,interval,dates):
    d=result(logged,date_from='2026-01-31',date_to='2026-02-02',interval=interval)
    assert [p['date'] for p in d['periods']]==dates
    assert d['totals_by_currency']==[] and all(p['units']==0 for p in d['periods'])
    p=stocked(logged,vehicle)
    sale_date('2026-02-01T12:00:00+00:00');assert sale(logged,p).status_code==200
    d=result(logged,date_from='2026-01-31',date_to='2026-02-02',interval=interval)
    assert d['sales_count']==1 and d['units']==1 and sum(p['units'] for p in d['periods'])==1


@pytest.mark.parametrize('day,times',[('2026-03-29',['2026-03-28T21:59:59+00:00','2026-03-28T22:00:00+00:00','2026-03-29T20:59:59+00:00','2026-03-29T21:00:00+00:00']),('2026-10-25',['2026-10-24T20:59:59+00:00','2026-10-24T21:00:00+00:00','2026-10-25T21:59:59+00:00','2026-10-25T22:00:00+00:00'])])
def test_kyiv_dst_inclusive_dates_exclusive_end(logged,vehicle,sale_date,day,times):
    p=stocked(logged,vehicle,quantity=4)
    for t in times:
        sale_date(t);assert sale(logged,p).status_code==200
    assert result(logged,date_from=day,date_to=day)['units']==2
    assert result(logged,date_from=day,date_to=day,tz='UTC')['units']==2


def test_tenant_and_financial_permissions(logged,vehicle,sale_date,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    p=stocked(logged,vehicle);assert sale(logged,p).status_code==200
    with TestClient(app) as c:
        assert c.get('/api/v1/sales/summary',params={'date_from':'2026-01-01','date_to':'2026-01-01'}).status_code==401
        signup(c,'other-summary@example.test');assert result(c)['units']==0
    required=['analytics.view','analytics.financial','sales.view','sales.view_financials']
    for missing in required:
        _,creds=employee(logged,[r for r in required if r!=missing])
        with activate(creds) as c:
            assert c.get('/api/v1/sales/summary',params={'date_from':'2026-01-01','date_to':'2026-01-01'}).status_code==403
    _,creds=employee(logged,required)
    with activate(creds) as c:assert result(c)['units']==1


@pytest.mark.parametrize('params',[{'date_from':'2026-02-02','date_to':'2026-02-01'},{'date_from':'2025-01-01','date_to':'2026-01-02'},{'interval':'hour'},{'tz':'unknown'},{'date_from':'0001-01-01'},{'date_to':'9999-12-31'}])
def test_bounded_request_validation(logged,params):
    r=logged.get('/api/v1/sales/summary',params={'date_from':'2026-01-01','date_to':'2026-01-01',**params})
    assert r.status_code==422,r.text


def test_real_statement_timeout_is_safe_and_connection_recovers(logged,monkeypatch):
    from sqlalchemy import text
    import app.services.sales_analytics as service
    monkeypatch.setattr(service,'AGGREGATE',text('SELECT pg_sleep(6)'))
    r=logged.get('/api/v1/sales/summary',params={'date_from':'2026-01-01','date_to':'2026-01-01'})
    assert r.status_code==503 and 'Скоротіть' in r.json()['detail']
    assert logged.get('/api/v1/dashboard').status_code==200
