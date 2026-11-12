"""Real disposable PostgreSQL: explicit inline presence + dismantling + existing ledger."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select,func
import pytest
from app.main import app
from app.db import engine
from app.models import DismantlingItem,Part,Operation,DismantlingRequest


def generate(c,v):
    path=f"/api/v1/vehicles/{v['id']}/dismantling-v3"
    p=c.post(path+'/preview',json={'facts':[],'universal':True});assert p.status_code==200,p.text
    r=c.post(path+'/save',json={'facts':[],'universal':True,'token':p.json()['token'],'confirm':True,'request_key':str(uuid4())});assert r.status_code==200,r.text
    return path,c.get(path).json()['items']

def prepare(c,path,ids,**extra):
    r=c.post(path+'/bulk/preview',json={'ids':ids,'action':'receipt','confirm_physical':True});assert r.status_code==200,r.text;p=r.json()
    return {'ids':ids,'action':'receipt','confirm_physical':True,'confirm':True,'etag':p['etag'],'preview_token':p['preview_token'],'request_key':str(uuid4()),'lines':[{'id':id,'quantity':extra.get('quantity',1),'confirm_physical':True} for id in p['eligible_ids']]},p

def test_five_unchecked_explicit_confirmation_and_replay(logged,vehicle):
    path,items=generate(logged,vehicle);ids=[i['id'] for i in items[:5]]
    old=logged.post(path+'/bulk/preview',json={'ids':ids,'action':'receipt'}).json();assert old['eligible']==0
    body,p=prepare(logged,path,ids,quantity=2);assert p['eligible']==5
    assert logged.get('/api/v1/parts').json()['total']==0
    bad={**body,'lines':[{**i,'confirm_physical':False} for i in body['lines']]}
    assert logged.post(path+'/bulk',json=bad).status_code==409
    r=logged.post(path+'/bulk',json=body);assert r.status_code==200,r.text;assert r.json()['updated']==5
    assert logged.post(path+'/bulk',json=body).json()==r.json()
    fresh,_=prepare(logged,path,ids);again=logged.post(path+'/bulk',json=fresh);assert again.status_code==200 and again.json()['updated']==0
    stock=logged.get('/api/v1/parts').json();assert stock['total']==5 and all(p['quantity']==2 for p in stock['items'])
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==5

def test_mixed_preserves_absent_excluded_damage_and_received(logged,vehicle):
    path,items=generate(logged,vehicle);ids=[i['id'] for i in items[:7]]
    first,_=prepare(logged,path,[ids[0]]);assert logged.post(path+'/bulk',json=first).status_code==200
    with Session(engine()) as db:
        for idx,inspection,included in [(1,'absent',True),(2,'unchecked',False),(3,'present',True)]:
            n=db.get(DismantlingItem,ids[idx]);n.plan_v3={**n.plan_v3,'inspection':inspection};n.included=included
        n=db.get(DismantlingItem,ids[4]);n.status='damaged';n.condition='damaged'
        db.commit()
    body,p=prepare(logged,path,ids);assert set(p['eligible_ids'])==set(ids[3:])
    r=logged.post(path+'/bulk',json=body);assert r.status_code==200,r.text
    assert r.json()['updated']==4 and r.json()['skipped']==3
    with Session(engine()) as db:
        damaged=db.get(DismantlingItem,ids[4]);assert db.get(Part,damaged.part_id).condition=='damaged'
        assert db.get(DismantlingItem,ids[1]).part_id is None and not db.get(DismantlingItem,ids[2]).included

def test_227_batches_replay_and_atomic_rollback(logged,vehicle,monkeypatch):
    from app.services import dismantling
    path,items=generate(logged,vehicle);ids=[i['id'] for i in items];assert len(ids)==227
    first,_=prepare(logged,path,ids[:100]);r=logged.post(path+'/bulk',json=first);assert r.status_code==200,r.text
    second,_=prepare(logged,path,ids[100:200]);original=dismantling.receipt;calls=[]
    def broken(*args,**kw):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('Injected local second-row failure')
        return original(*args,**kw)
    monkeypatch.setattr(dismantling,'receipt',broken)
    with pytest.raises(RuntimeError):logged.post(path+'/bulk',json=second)
    assert logged.get('/api/v1/parts?limit=1').json()['total']==100
    monkeypatch.setattr(dismantling,'receipt',original)
    for body in [first,second]:
        r=logged.post(path+'/bulk',json=body);assert r.status_code==200,r.text
    third,_=prepare(logged,path,ids[200:]);r=logged.post(path+'/bulk',json=third);assert r.status_code==200,r.text
    assert logged.get('/api/v1/parts?limit=1').json()['total']==227
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==227

def test_concurrent_receipt_one_winner_no_duplicate(logged,vehicle):
    path,items=generate(logged,vehicle);body,_=prepare(logged,path,[items[0]['id']])
    def send(key):
        with TestClient(app) as c:
            c.cookies.update(dict(logged.cookies));c.headers.update(dict(logged.headers));r=c.post(path+'/bulk',json={**body,'request_key':key});return r.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,[str(uuid4()),str(uuid4())]))
    assert sorted(codes)==[200,409]
    assert logged.get('/api/v1/parts').json()['total']==1

def test_sources_owner_only_unique_and_not_leaked(logged,vehicle,monkeypatch):
    path,items=generate(logged,vehicle)
    assert logged.get(path+'/sources').status_code==403
    legacy=logged.post('/api/v1/vehicles/'+vehicle['id']+'/dismantling-preview',json={'facts':[]});assert legacy.status_code==200,legacy.text
    assert all(i['source']==[] for i in legacy.json()['items'])
    assert logged.get(path).json()['items'][0]['sources']==[]
    preview=logged.post(path+'/preview',json={'facts':[],'universal':True}).json()
    assert preview['proposals'][0]['item']['source']==[]
    assert preview['catalogue_status']['generator']['gaps']==[]
    assert not {'baseline_positions','published_reference_positions','exact_source_positions'}&preview['catalogue_status']['generator'].keys()
    assert logged.get('/api/v1/vehicles/'+vehicle['id']).json()['dismantling_v3']['generator_status']['sources']==[]
    me=logged.get('/api/v1/auth/me').json();monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',me['id'])
    with Session(engine()) as db:
        n=db.get(DismantlingItem,items[0]['id']);snap={**n.plan_v3['snapshot'],'source':[{'kind':'base','key':'one'},{'kind':'base','key':'duplicate'},{'kind':'global_modification','key':'other'}]};n.plan_v3={**n.plan_v3,'snapshot':snap};db.commit()
    r=logged.get(path+'/sources');assert r.status_code==200,r.text;assert sum(r.json()['counts'].values())==227 and r.json()['counts']['multiple_sources']==1
    assert logged.get(path).json()['items'][0]['sources']

def test_employee_sources_denied_and_legacy_bulk_fingerprint_preserved(logged,vehicle,monkeypatch):
    from test_team import employee,activate
    from app.schemas.dismantling_v3 import BulkCommand
    from app.services.catalogue_format import digest
    path,items=generate(logged,vehicle);ids=[items[0]['id']]
    listing=logged.get(path).json();present={'ids':ids,'action':'present','etag':listing['etag'],'request_key':str(uuid4())}
    assert logged.post(path+'/bulk',json=present).status_code==200
    p=logged.post(path+'/bulk/preview',json={'ids':ids,'action':'receipt'}).json()
    body={'ids':ids,'action':'receipt','etag':p['etag'],'preview_token':p['preview_token'],'request_key':str(uuid4()),'confirm':True,'lines':[{'id':ids[0],'quantity':1}]}
    r=logged.post(path+'/bulk',json=body);assert r.status_code==200,r.text
    old=BulkCommand.model_validate(body).model_dump(mode='json');old.pop('confirm_physical')
    for line in old['lines']:line.pop('confirm_physical')
    actor=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        request=db.scalar(select(DismantlingRequest).where(DismantlingRequest.request_key==body['request_key']))
        assert request.request_sha==digest(['bulk',vehicle['id'],actor,old])
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    row,credentials=employee(logged,permissions=['vehicles.view','catalog.view','inventory.view'])
    with activate(credentials) as worker:
        assert worker.get(path+'/sources').status_code==403
        assert worker.get(path).json()['items'][0]['sources']==[]
