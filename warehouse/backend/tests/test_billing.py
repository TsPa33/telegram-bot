"""Local PostgreSQL mock-contract tests. No provider network or credentials."""
import base64,json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account,Vehicle,WorkspaceSubscription,BillingPayment,DismantlingCredit,DismantlingUsage,VehicleChecklistItem,now
from app.services import billing,checklists
from app.services.plan_parts import CatalogPartType

@pytest.fixture
def scope(logged,vehicle,monkeypatch):
    owner=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        db.get(Vehicle,vehicle['id']).ktype=123;db.commit()
    logged.headers['Origin']='https://testserver'
    monkeypatch.setenv('WAREHOUSE_PUBLIC_ORIGIN','https://testserver')
    for k,v in {'WAREHOUSE_ENV':'staging','WAREHOUSE_BILLING_ENABLED':'true','WAREHOUSE_BILLING_FIXTURE_CONTRACT':'true'}.items():monkeypatch.setenv(k,v)
    return logged,owner,vehicle['id']

def pay(db,owner,product,event=None):
    amount=billing.PLANS[product]['amount'] if product in billing.PLANS else billing.PACKS[product][0]
    p=BillingPayment(workspace_id=owner,request_key=str(uuid4()),product=product,amount=amount,currency='UAH');db.add(p);db.commit()
    payload={'order_id':p.id,'amount':str(amount),'currency':'UAH','status':'sandbox','sandbox':1,'payment_id':'fixture-only'}
    billing.process_event(db,payload,event or str(uuid4()));return p,payload

@pytest.mark.parametrize('plan,credits,limit',[('standard',10,5),('premium',50,10)])
def test_plan_and_duplicate_event(scope,plan,credits,limit):
    _,owner,_=scope
    with Session(engine()) as db:
        p,payload=pay(db,owner,plan,'same-event')
        assert billing.process_event(db,payload,'same-event')=='duplicate'
        assert billing.process_event(db,payload,'late-duplicate')=='already_confirmed'
        assert billing.balance(db,owner)=={'monthly':credits,'extra':0}
        assert db.scalar(select(func.count()).select_from(DismantlingCredit))==1
        assert billing.PLANS[db.get(WorkspaceSubscription,owner).plan]['employees']==limit

@pytest.mark.parametrize('product,quantity',[('pack_1',1),('pack_5',5),('pack_10',10)])
def test_packs_do_not_reset(scope,product,quantity):
    _,owner,_=scope
    with Session(engine()) as db:
        pay(db,owner,product);assert billing.balance(db,owner)['extra']==quantity
        assert not billing.active(billing.subscription(db,owner))
        pay(db,owner,'standard');assert billing.balance(db,owner)=={'monthly':10,'extra':quantity}

@pytest.mark.parametrize('patch',[{'amount':'999'},{'currency':'USD'},{'status':'success'},{'sandbox':0}])
def test_invalid_event(scope,patch):
    _,owner,_=scope
    with Session(engine()) as db:
        p=BillingPayment(workspace_id=owner,request_key=str(uuid4()),product='standard',amount=1000,currency='UAH');db.add(p);db.commit()
        with pytest.raises(HTTPException):billing.process_event(db,{'order_id':p.id,'amount':'1000','currency':'UAH','status':'sandbox','sandbox':1,**patch},str(uuid4()))
        db.rollback();assert billing.subscription(db,owner) is None

def test_failure_and_signature(scope):
    _,owner,_=scope
    with Session(engine()) as db:
        p=BillingPayment(workspace_id=owner,request_key=str(uuid4()),product='standard',amount=1000,currency='UAH');db.add(p);db.commit()
        billing.process_event(db,{'order_id':p.id,'amount':1000,'currency':'UAH','sandbox':1,'status':'failure'},str(uuid4()))
        assert billing.subscription(db,owner) is None
    data=base64.b64encode(json.dumps({'order_id':'fixture'}).encode()).decode()
    assert billing.decode(data,billing.signature(data,'fixture-secret'),'fixture-secret')['order_id']=='fixture'
    with pytest.raises(HTTPException):billing.decode(data,'forged','fixture-secret')

class Catalogue:
    last_metadata={'completeness':'complete'}
    calls=0
    def categories(self,*args):self.calls+=1;return [CatalogPartType(pt_id=1,name='Starter',article_count=3)]

def test_catalogue_credit_and_reopen(scope):
    _,owner,vehicle=scope
    with Session(engine()) as db:
        pay(db,owner,'standard');client=Catalogue();result=checklists.generate(db,vehicle,owner,client);db.commit()
        assert result['total']==1 and billing.balance(db,owner)['monthly']==9
        checklists.generate(db,vehicle,owner,client);db.commit()
        assert client.calls==1 and billing.balance(db,owner)['monthly']==9
        assert db.scalar(select(func.count()).select_from(DismantlingUsage).where(DismantlingUsage.status=='done'))==1

@pytest.mark.parametrize('mode',['error','partial'])
def test_failed_or_partial_no_loss(scope,mode):
    _,owner,vehicle=scope
    class Broken(Catalogue):
        last_metadata={'completeness':'partial'}
        def categories(self,*args):
            if mode=='error':raise TimeoutError('fixture timeout')
            return super().categories(*args)
    with Session(engine()) as db:
        pay(db,owner,'standard')
        with pytest.raises((HTTPException,TimeoutError)):checklists.generate(db,vehicle,owner,Broken())
        assert billing.balance(db,owner)['monthly']==10
        assert not db.scalar(select(func.count()).select_from(VehicleChecklistItem).where(VehicleChecklistItem.vehicle_id==vehicle))

def test_concurrent_reservation_and_restart(scope):
    _,owner,vehicle=scope
    with Session(engine()) as db:pay(db,owner,'standard')
    def reserve():
        with Session(engine()) as db:
            try:return billing.reserve(db,owner,vehicle,123)
            except HTTPException as e:db.rollback();return e.status_code
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:reserve(),range(2)))
    assert sum(isinstance(x,str) for x in results)==1 and 409 in results
    with Session(engine()) as db:
        checklists.generate(db,vehicle,owner,Catalogue(),preloaded_rows=Catalogue().categories(),charge=False);db.commit()
        assert billing.balance(db,owner)['monthly']==9

def test_employee_expiry_and_bypass(scope,monkeypatch):
    client,owner,_=scope
    with Session(engine()) as db:
        pay(db,owner,'standard')
        for i in range(5):db.add(Account(name='Employee',email=f'{i}@fixture.test',password_hash='not-a-login',workspace_account_id=owner,role='MANAGER',permissions=[],is_active=True))
        db.commit()
        with pytest.raises(HTTPException):billing.employee_limit(db,owner)
        db.rollback();employee=db.scalar(select(Account).where(Account.workspace_account_id==owner));employee.is_active=False;db.commit();billing.employee_limit(db,owner)
        db.rollback();db.get(WorkspaceSubscription,owner).period_end=now()-timedelta(days=1);db.commit()
    assert client.get('/api/v1/vehicles').status_code==200
    assert client.post('/api/v1/parts',json={'name':'No write'}).status_code==402
    assert client.post('/api/v1/billing/checkout').status_code==503
    monkeypatch.setenv('WAREHOUSE_BILLING_DEMO_WORKSPACES',owner)
    assert client.post('/api/v1/parts',json={'name':'Explicit demo bypass'}).status_code==201
    monkeypatch.setenv('WAREHOUSE_ENV','production');assert not billing.enabled() and not billing.exempt(owner)

def test_disabled_provider_and_staff_financial_access(scope):
    client,owner,_=scope
    assert client.post('/api/v1/billing/callback',data={'data':'forged','signature':'bad'}).status_code==503
    assert not client.get('/api/v1/billing/status').json()['checkout_available']
    with Session(engine()) as db:
        from app.services.auth import hasher
        db.add(Account(name='Manager',email='manager@fixture.test',password_hash=hasher.hash('long-fixture-password'),workspace_account_id=owner,role='MANAGER',permissions=['inventory.view'],is_active=True));db.commit()
    client.post('/api/v1/auth/logout')
    r=client.post('/api/v1/auth/login',json={'email':'manager@fixture.test','password':'long-fixture-password'});assert r.status_code==200
    client.headers['X-CSRF-Token']=r.json()['csrf_token']
    assert client.get('/api/v1/billing/payments').status_code==403
    staff=client.get('/api/v1/billing/status').json();assert 'plans' not in staff and not staff['can_manage']

def test_grace_and_calendar(scope,monkeypatch):
    _,owner,_=scope
    with Session(engine()) as db:
        pay(db,owner,'standard');s=db.get(WorkspaceSubscription,owner);s.auto_renew=True;s.provider_id='fixture-subscription';s.period_end=now()-timedelta(days=1);db.commit()
        billing.mark_renewal_failed(db,owner,'fixture-subscription');db.commit();assert billing.active(billing.subscription(db,owner))
        end=s.grace_end;billing.mark_renewal_failed(db,owner,'fixture-subscription');db.commit();assert s.grace_end==end
        monkeypatch.setenv('WAREHOUSE_BILLING_GRACE_DAYS','0');billing.mark_renewal_failed(db,owner,'fixture-subscription');db.commit();assert not billing.active(billing.subscription(db,owner))
    from datetime import datetime,timezone
    assert billing.next_month(datetime(2028,1,31,tzinfo=timezone.utc)).day==29
    assert billing.next_month(datetime(2026,12,31,tzinfo=timezone.utc)).year==2027

def test_fixture_contract_cannot_enable_real_staging(monkeypatch):
    monkeypatch.setenv('WAREHOUSE_ENV','staging');monkeypatch.setenv('WAREHOUSE_BILLING_ENABLED','true');monkeypatch.delenv('WAREHOUSE_BILLING_FIXTURE_CONTRACT',raising=False)
    assert not billing.enabled()

@pytest.mark.parametrize('plan,n',[('standard',10),('premium',50)])
def test_quota_and_monthly_before_extra(scope,plan,n):
    _,owner,vehicle=scope
    with Session(engine()) as db:
        pay(db,owner,plan);pay(db,owner,'pack_1')
        for i in range(n):
            db.get(Vehicle,vehicle).ktype=1000+i;db.commit();u=billing.reserve(db,owner,vehicle,1000+i);billing.finalize(db,owner,u,complete=True);db.commit()
        assert billing.balance(db,owner)=={'monthly':0,'extra':1}
        db.get(Vehicle,vehicle).ktype=2000;db.commit();u=billing.reserve(db,owner,vehicle,2000);billing.finalize(db,owner,u,complete=True);db.commit()
        assert billing.balance(db,owner)=={'monthly':0,'extra':0}
        db.get(Vehicle,vehicle).ktype=2001;db.commit()
        with pytest.raises(HTTPException) as error:billing.reserve(db,owner,vehicle,2001)
        assert error.value.status_code==402

def test_workspace_isolation(scope):
    _,owner,vehicle=scope
    with Session(engine()) as db:
        other=Account(name='Other',email='other@fixture.test',password_hash='not-a-login');db.add(other);db.commit();pay(db,other.id,'standard')
        with pytest.raises(HTTPException) as error:billing.reserve(db,other.id,vehicle,123)
        assert error.value.status_code==404

def test_history_survives_disabled_enforcement(scope,monkeypatch):
    client,owner,_=scope
    with Session(engine()) as db:pay(db,owner,'standard')
    monkeypatch.setenv('WAREHOUSE_BILLING_ENABLED','false')
    response=client.get('/api/v1/billing/payments');assert response.status_code==200
    assert response.json()['total']==1
    assert client.get('/api/v1/billing/status').json()['credits']['monthly']==10

def test_credit_requires_distinct_user_confirmation(scope):
    client,owner,vehicle=scope
    with Session(engine()) as db:pay(db,owner,'standard')
    response=client.post(f'/api/v1/plan-parts/categories/lookup?vehicle_id={vehicle}&ktype=123')
    assert response.status_code==409
    assert '1 розбору' in response.json()['detail']
    with Session(engine()) as db:assert billing.balance(db,owner)['monthly']==10

def test_empty_catalogue_does_not_consume(scope):
    _,owner,vehicle=scope
    class Empty(Catalogue):
        def categories(self,*args):return []
    with Session(engine()) as db:
        pay(db,owner,'standard')
        with pytest.raises(HTTPException):checklists.generate(db,vehicle,owner,Empty())
        assert billing.balance(db,owner)['monthly']==10
