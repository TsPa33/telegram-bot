"""R5 synthetic fixtures only; no live source requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from app.models import Account,Part
from app.models.catalogue import CataloguePrice
from app.services.auth import hasher
from app.services.market_check import source_url
from app.services.price_guidance import utcnow
from test_stage3c import setup,item
from test_catalogue_v2 import platform
from test_v3_release_audit import all_tables
from conftest import signup

def check(c,p):return c.post('/api/v1/parts/'+p+'/market-refresh',json={})

def test_projection_dual_currency_and_replay_no_writes(platform,vehicle,monkeypatch):
    import socket
    p=setup(platform,vehicle,[{**item(i),'price_usd':'10'} for i in range(3)])
    with Session(engine()) as db:before=all_tables(db)
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:(_ for _ in ()).throw(AssertionError('External HTTP forbidden')))
    r=check(platform,p);assert r.status_code==200,r.text
    data=r.json();assert data['mode']=='imported_catalogue' and not data['fresh_data_fetched'] and not data['cached']
    assert not data['live_refresh_available'] and data['source_status']=='source_unavailable'
    assert data['result_source']=='imported'
    assert data['offer_count']==3 and len(data['offers'])==6
    assert data['guidance']['level']=='A' and len(data['guidance']['cohorts'])==2
    assert data['observed_at']!=data['checked_at'] and data['external_url']=='https://aleto.ua/'
    assert check(platform,p).json()['context_token']==data['context_token']
    with Session(engine()) as db:assert all_tables(db)==before

def test_historical_and_context_invalidation(platform,vehicle,monkeypatch):
    p=setup(platform,vehicle,[item(i) for i in range(3)]);initial=check(platform,p).json()
    from app.services import price_guidance
    future=utcnow()+timedelta(days=120)
    monkeypatch.setattr(price_guidance,'utcnow',lambda:future)
    with Session(engine()) as db:before=all_tables(db)
    old=check(platform,p).json();assert old['guidance']['level']=='D' and old['guidance']['cohorts']==[]
    assert len(old['offers'])==3 and all(x['status']=='historical_not_recommendation' for x in old['offers'])
    assert old['context_token']!=initial['context_token']
    with Session(engine()) as db:
        assert all_tables(db)==before
        db.get(Part,p).oem_number='UNKNOWN';db.commit()
    changed=check(platform,p).json();assert changed['context_token']!=old['context_token'] and changed['guidance']['level']!='A'

def test_access_and_tenant(platform,vehicle):
    p=setup(platform,vehicle,[item(0)]);owner=platform.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:db.add(Account(email='r5-reader@example.test',name='Reader',password_hash=hasher.hash('local-reader-password'),role='MANAGER',workspace_account_id=owner,permissions=['inventory.view','catalog.view']));db.commit()
    with TestClient(app) as reader:
        login=reader.post('/api/v1/auth/login',json={'email':'r5-reader@example.test','password':'local-reader-password'});reader.headers['X-CSRF-Token']=login.json()['csrf_token']
        assert check(reader,p).status_code==403
        assert reader.get('/api/v1/parts/'+p+'/price-guidance').status_code==200
        with Session(engine()) as db:a=db.scalar(select(Account).where(Account.email=='r5-reader@example.test'));a.permissions=['inventory.view','catalog.view','market.check'];db.commit()
        assert check(reader,p).status_code==200
        reader.headers.pop('X-CSRF-Token');assert check(reader,p).status_code==403
    with TestClient(app) as other:signup(other,'r5-other@example.test');assert check(other,p).status_code==404
    assert platform.post('/api/v1/parts/'+p+'/market-refresh',json={'url':'http://127.0.0.1/'}).status_code==422

def test_concurrent_no_mutations(platform,vehicle):
    p=setup(platform,vehicle,[item(0)])
    with Session(engine()) as db:before=all_tables(db)
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:check(platform,p),range(2)))
    assert all(r.status_code==200 for r in rows) and rows[0].json()['context_token']==rows[1].json()['context_token']
    with Session(engine()) as db:assert all_tables(db)==before

@pytest.mark.parametrize('url',['http://aleto.ua/x','https://aleto.ua.evil.test/x','https://127.0.0.1/x','https://user@aleto.ua/x','https://aleto.ua:444/x','file:///tmp/a','javascript:alert(1)','https://aleto.ua:bad/x'])
def test_untrusted_links(url):assert source_url(url) is None

def test_allowed_link():assert source_url('https://aleto.ua/offer/test')=='https://aleto.ua/offer/test'


def test_non_aleto_links_never_become_aleto_recommendation(platform,vehicle,monkeypatch):
    from app.services import market_check
    p=setup(platform,vehicle,[item(0)])
    monkeypatch.setattr(market_check,'guidance',lambda *a,**k:{p:dict(level='A',cohorts=[dict(examples=[dict(source='untrusted',article='x',currency='UAH',amount='100',observed_at=utcnow().isoformat(),url='https://other.test/')])],examples=[],offer_count=1,reasons={})})
    r=check(platform,p);assert r.status_code==200,r.text
    data=r.json();assert data['result_source']=='unavailable'
    assert data['status']=='no_matches' and not data['offers'] and data['guidance']['level']=='D' and not data['guidance']['cohorts']
