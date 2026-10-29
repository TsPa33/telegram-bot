"""Bounded atomic bulk commands: selection, receipt, physical counters and isolation."""
import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.main import app
from app.models import Vehicle,Part,Operation
from test_stage2d import fixture_catalogue,candidate,quick
from test_dismantling_plan_v3 import get
from test_v3_release_audit import all_tables


def seed(c,v,monkeypatch,n=5):
    rows=[candidate(f'Тестова деталь {i:04d}') for i in range(n)]
    for i,r in enumerate(rows):r.update(category='Категорія '+str(i%3),subcategory='Підкатегорія '+str(i%2),reference_prices=[{'median':'9999.00'}])
    fixture_catalogue(monkeypatch,rows);r=quick(c,v);assert r.status_code==200,r.text
    return get(c,v)['items']


def preview(c,v,ids,action='receipt'):
    r=c.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/bulk/preview",json=dict(ids=ids,action=action));assert r.status_code==200,r.text;return r.json()
def command(c,v,ids,action,**kw):
    p=preview(c,v,ids,action)
    data=dict(ids=ids,action=action,etag=p['etag'],request_key=str(uuid4()),reason='Явне тестове рішення',confirm=action in ('receipt','dismantled'))
    if action=='receipt':data.update(preview_token=p['preview_token'],lines=[dict(id=id,quantity=1) for id in p['eligible_ids']])
    data.update(kw)
    return c.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/bulk",json=data)


def test_selection_includes_all_not_rendered_60_filters_and_pagination(client,vehicle,monkeypatch):
    items=seed(client,vehicle,monkeypatch,1120);path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/selection"
    first=client.get(path).json();second=client.get(path,params={'offset':1000}).json()
    assert first['available']==1120 and len(first['ids'])==1000 and len(second['ids'])==120
    assert len(set(first['ids']+second['ids']))==1120
    for params in [dict(category='Категорія 0'),dict(category='Категорія 0',subcategory='Підкатегорія 1'),dict(q='деталь 00'),dict(status='unchecked')]:
        r=client.get(path,params=params).json()
        expected=[i['id'] for i in items if (not params.get('category') or i['category']==params['category']) and (not params.get('subcategory') or i['subcategory']==params['subcategory']) and (not params.get('q') or params['q'] in i['name'])]
        assert r['available']==len(expected)
        assert set(r['ids'])==set(expected[:1000])
    assert client.get(path,params={'limit':1001}).status_code==422
    assert command(client,vehicle,[i['id'] for i in items[:1000]],'present').json()['updated']==1000
    assert command(client,vehicle,[i['id'] for i in items[1000:]],'present').json()['updated']==120
    assert get(client,vehicle)['counts']['confirmed']==1120


def test_196_unchecked_then_194_user_confirmed_reload_and_generator_keeps_counts(client,vehicle,monkeypatch):
    rows=[candidate('Контрольна деталь '+str(i)) for i in range(196)]
    for r in rows:r['applicability_status']='confirmed'  # Fitment alone must never become presence.
    fixture_catalogue(monkeypatch,rows);assert quick(client,vehicle).status_code==200
    current=get(client,vehicle);assert current['counts']['unchecked']==196 and current['counts']['confirmed']==0 and current['counts']['in_stock']==0
    ids=[i['id'] for i in current['items'][:194]];assert command(client,vehicle,ids,'present').json()['updated']==194
    current=get(client,vehicle);assert current['counts']['confirmed']==194 and current['counts']['unchecked']==2
    assert all(i['confirmation_source']=='user_decision' for i in current['items'] if i['inspection']=='present')
    assert quick(client,vehicle).status_code==200
    current=get(client,vehicle);assert current['counts']['confirmed']==194 and current['counts']['unchecked']==2 and current['counts']['in_stock']==0


def test_mixed_receipt_quantities_fields_ledger_inventory_and_replays(client,vehicle,monkeypatch):
    items=seed(client,vehicle,monkeypatch);ids=[i['id'] for i in items]
    assert command(client,vehicle,ids[:3],'present').json()['updated']==3
    assert command(client,vehicle,ids[:2],'dismantled').json()['updated']==2
    p=preview(client,vehicle,ids);assert (p['selected'],p['confirmed'],p['dismantled'],p['received'],p['eligible'])==(5,3,2,0,2)
    assert len(p['blocked'])==3
    lines=[dict(id=ids[0],quantity=2,condition='new',location='Полиця A',selling_price='25.90'),dict(id=ids[1],quantity=5,condition='used',location='Полиця Б')]
    body=dict(ids=ids,action='receipt',etag=p['etag'],preview_token=p['preview_token'],request_key=str(uuid4()),confirm=True,lines=lines)
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/bulk"
    r=client.post(path,json=body);assert r.status_code==200,r.text
    assert r.json()['updated']==2 and r.json()['skipped']==3 and len(r.json()['part_ids'])==2
    assert client.post(path,json=body).json()==r.json()
    with Session(engine()) as db:
        parts=[db.get(Part,id) for id in r.json()['part_ids']]
        assert [p.quantity for p in parts]==[2,5] and parts[0].selling_price==__import__('decimal').Decimal('25.90')
        assert parts[0].condition=='new' and parts[0].location=='Полиця A'
        assert parts[1].selling_price is None and all(p.unit_cost is None for p in parts)
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==2
        before_parts=[(p.id,p.quantity,p.selling_price) for p in parts];before_ops={r.id:str(r.after) for r in db.scalars(select(Operation))}
    stock=client.get('/api/v1/parts').json();assert stock['total']==2 and sorted(i['quantity'] for i in stock['items'])==[2,5]
    repeated=command(client,vehicle,ids,'receipt');assert repeated.status_code==200 and repeated.json()['updated']==0
    with Session(engine()) as db:
        assert before_parts==[(db.get(Part,id).id,db.get(Part,id).quantity,db.get(Part,id).selling_price) for id,_,_ in before_parts]
        assert before_ops=={r.id:str(r.after) for r in db.scalars(select(Operation))}


def test_protected_archived_and_excluded_reasons_are_not_mutated(client,vehicle,monkeypatch):
    ids=[i['id'] for i in seed(client,vehicle,monkeypatch,3)]
    command(client,vehicle,ids[:1],'present');command(client,vehicle,ids[:1],'dismantled');received=command(client,vehicle,ids[:1],'receipt').json()
    with Session(engine()) as db:db.get(Part,received['part_ids'][0]).archived=True;db.commit()
    command(client,vehicle,ids[1:2],'exclude');p=preview(client,vehicle,ids,'present')
    assert p['eligible_ids']==[ids[2]] and {r['id'] for r in p['blocked']}==set(ids[:2])
    before=get(client,vehicle);assert command(client,vehicle,ids,'present').json()['updated']==1
    after=get(client,vehicle)
    for id in ids[:2]:assert next(i for i in after['items'] if i['id']==id)==next(i for i in before['items'] if i['id']==id)


def test_receipt_rollback_covers_already_flushed_first_line(client,vehicle,monkeypatch):
    ids=[i['id'] for i in seed(client,vehicle,monkeypatch,2)];command(client,vehicle,ids,'present');command(client,vehicle,ids,'dismantled')
    from app.services import dismantling
    real=dismantling.receipt;calls=[]
    def fail(*args,**kw):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('Injected second receipt failure')
        return real(*args,**kw)
    monkeypatch.setattr(dismantling,'receipt',fail)
    with Session(engine()) as db:before=all_tables(db)
    with pytest.raises(RuntimeError,match='second receipt'):command(client,vehicle,ids,'receipt')
    with Session(engine()) as db:assert all_tables(db)==before


def test_receipt_concurrency_stale_and_changed_key_payload(client,vehicle,monkeypatch):
    ids=[i['id'] for i in seed(client,vehicle,monkeypatch,1)];command(client,vehicle,ids,'present');command(client,vehicle,ids,'dismantled');p=preview(client,vehicle,ids)
    body=dict(ids=ids,action='receipt',etag=p['etag'],preview_token=p['preview_token'],request_key=str(uuid4()),confirm=True,lines=[dict(id=ids[0],quantity=3)])
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/bulk"
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:client.post(path,json=body),range(2)))
    assert all(r.status_code==200 for r in results) and results[0].json()==results[1].json()
    assert client.post(path,json={**body,'request_key':str(uuid4())}).status_code==409
    assert client.post(path,json={**body,'lines':[dict(id=ids[0],quantity=9)]}).status_code==409
    with Session(engine()) as db:assert db.scalar(select(Part.quantity))==3 and db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1


def test_permission_fields_csrf_and_workspace(client,vehicle,monkeypatch):
    ids=[i['id'] for i in seed(client,vehicle,monkeypatch,1)];command(client,vehicle,ids,'present');command(client,vehicle,ids,'dismantled')
    from test_team import employee,activate
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    _,data=employee(client,['vehicles.view','catalog.view','dismantling.manage','inventory.create','inventory.adjust_quantity']);low=activate(data)
    try:
        for fields in [dict(selling_price='1.00'),dict(location='A'),dict(condition='new')]:
            assert command(low,vehicle,ids,'receipt',lines=[dict(id=ids[0],quantity=1,**fields)]).status_code==403
        assert command(low,vehicle,ids,'receipt').status_code==200
    finally:low.close()
    csrf=client.headers.pop('X-CSRF-Token');assert command_preview_status(client,vehicle,ids)==403;client.headers['X-CSRF-Token']=csrf
    with TestClient(app) as other:
        a=other.post('/api/v1/auth/register',json=dict(name='Other bulk workspace',email='bulk-other@example.test',password='local-long-password')).json();other.headers['X-CSRF-Token']=a['csrf_token']
        assert command_preview_status(other,vehicle,ids)==404
        assert other.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/selection").status_code==404


def command_preview_status(c,v,ids):return c.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/bulk/preview",json=dict(ids=ids,action='receipt')).status_code


def test_explicit_confirmation_and_limits_reject_before_mutation(client,vehicle,monkeypatch):
    ids=[i['id'] for i in seed(client,vehicle,monkeypatch,1)];command(client,vehicle,ids,'present');command(client,vehicle,ids,'dismantled');p=preview(client,vehicle,ids)
    body=dict(ids=ids,action='receipt',etag=p['etag'],preview_token=p['preview_token'],request_key=str(uuid4()),confirm=True,lines=[dict(id=ids[0],quantity=1)])
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/bulk"
    for patch in [dict(confirm=False),dict(lines=[dict(id=ids[0],quantity=0)]),dict(lines=[dict(id=ids[0],quantity=1,selling_price='-1')]),dict(ids=[str(i) for i in range(1001)]),dict(actor_id='foreign')]:
        assert client.post(path,json={**body,**patch}).status_code==422
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0
