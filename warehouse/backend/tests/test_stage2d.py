"""Quick commands against disposable PostgreSQL. No live catalogue publication."""
import copy,json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from pathlib import Path
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Vehicle,DismantlingItem,Part,Operation,DismantlingRequest
from app.models.canonical import CanonicalState
from app.services import dismantling_plan_v3 as service
from app.services.dismantling_preview import configuration
from app.services.canonical_rules import sid,placement,RULE_FINGERPRINT,TYPES
from app.services.canonical_applicability import assess
from test_dismantling_plan_v3 import get,decision,preview as checked
from test_v3_release_audit import all_tables


def candidate(name,tid=None,side='unknown',position='unknown'):
    tid=tid or sid('stage2d-synthetic-type',name)
    pos=placement(dict(type_id=tid,installation=dict(side=side,position=position,mount=[])))
    return dict(id=pos['id'],canonical_part_type_id=tid,name=name,category='Синтетична конструкція',subcategory='Локальний тест',installation_position=pos,quantity=None,variants=[],source=[dict(kind='base',key='synthetic:'+pos['id'])],reference_prices=[],applicability_status='unknown',applicability=dict(conflicting_fields=[]),explanation='Synthetic possible component; not real fitment')


def fixture_catalogue(monkeypatch,items):
    # Seed only isolated test reference state; never invoke a publish operation.
    with Session(engine()) as db:
        state=db.get(CanonicalState,1);state.snapshot_sha='d'*64;state.policy={'rules_sha':RULE_FINGERPRINT};db.commit()
    def generate(db,v,workspace,facts,selected):
        config=configuration(db,v,workspace,facts,selected)
        rows=copy.deepcopy(items(config) if callable(items) else items)
        return dict(items=rows,total=len(rows),configuration=config,snapshot_sha='d'*64,published=True,fallback_used=False)
    monkeypatch.setattr(service,'preview',generate)


def quick(c,v,**kw):
    payload=dict(facts=[],etag=get(c,v)['etag'],request_key=str(uuid4()),confirm=True);payload.update(kw)
    return c.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/quick",json=payload)


def test_336_candidates_140_review_create_196_and_persist_pending(client,vehicle,monkeypatch,tmp_path):
    items=[candidate(f'Синтетична незалежна деталь {i}') for i in range(196)]
    for i in range(70):
        name=f'Синтетична неоднозначна функція {i}';items += [candidate(name),candidate(name,side='left')]
    fixture_catalogue(monkeypatch,items)
    p=checked(client,vehicle);assert p['counts']['proposed']==336 and p['counts']['new']==196 and p['counts']['review']==140
    with Session(engine()) as db:before=all_tables(db)
    r=quick(client,vehicle);assert r.status_code==200,r.text
    assert r.json()['created']==196 and r.json()['pending']==140 and r.json()['received']==0
    state=get(client,vehicle);assert state['total']==196 and state['pending_count']==140
    assert all(i['inspection']=='unchecked' for i in state['items'])
    assert all(i['status']=='pending_review' and i['reason'] and i['needs'] for i in state['pending_review'])
    again=quick(client,vehicle);assert again.status_code==200 and again.json()['created']==0
    current=get(client,vehicle);assert current['total']==196 and current['pending_count']==140
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==0
        assert db.get(Vehicle,vehicle['id']).dismantling_v3['skipped']=={}
        after=all_tables(db);assert before['parts']==after['parts']
    dest=Path(os.environ.get('WAREHOUSE_STAGE2D_EVIDENCE',str(tmp_path/'quick-336.json')))
    dest.write_text(json.dumps(dict(synthetic=True,real_B_tested=False,candidates=336,planner_new=196,planner_review=140,created=196,pending=140,repeat_created=again.json()['created'],received=0),indent=2)+'\n')


def test_whole_overlap_component_not_just_planner_review(monkeypatch,client,vehicle):
    # Exercise a mislabeled safe-looking neighbor: policy independently fences it.
    fixture_catalogue(monkeypatch,[candidate('Generic'),candidate('Generic',side='left')])
    real=service.make_preview
    def optimistic(*a,**kw):
        p=real(*a,**kw);p['proposals'][0]['action']='new';return p
    monkeypatch.setattr(service,'make_preview',optimistic)
    r=quick(client,vehicle);assert r.status_code==200,r.text
    assert r.json()['created']==0 and r.json()['pending']==2
    assert get(client,vehicle)['total']==0


def test_same_request_replay_stale_commands_and_races(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Only safe item')]);etag=get(client,vehicle)['etag'];key=str(uuid4())
    payload=dict(facts=[],etag=etag,request_key=key,confirm=True)
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/quick"
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:client.post(path,json=payload),range(2)))
    assert all(r.status_code==200 for r in results) and results[0].json()==results[1].json()
    assert get(client,vehicle)['total']==1
    assert client.post(path,json={**payload,'request_key':str(uuid4())}).status_code==409
    assert client.post(path,json={**payload,'facts':[dict(field='powertrain',value='diesel',kind='manual',reference='Local test',confidence='reported')]}).status_code==409
    # Distinct concurrent commands from one state: one success, one stale 409.
    fresh=get(client,vehicle)['etag']
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:client.post(path,json={**payload,'etag':fresh,'request_key':str(uuid4())}),range(2)))
    assert sorted(r.status_code for r in results)==[200,409]
    assert get(client,vehicle)['total']==1


def test_failure_after_rows_and_audit_flush_rolls_back(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Rollback row')])
    with Session(engine()) as db:before=all_tables(db)
    def fail(db,*args):
        if any(isinstance(r,DismantlingRequest) for r in db.new):raise RuntimeError('Injected failure before replay commit')
    event.listen(Session,'before_flush',fail)
    try:
        with pytest.raises(RuntimeError,match='Injected failure'):quick(client,vehicle)
    finally:event.remove(Session,'before_flush',fail)
    with Session(engine()) as db:assert all_tables(db)==before


def test_empty_unpublished_and_fail_closed_access(client,vehicle,monkeypatch):
    r=quick(client,vehicle);assert r.status_code==409 and 'не опубліковано' in r.json()['detail']
    assert not get(client,vehicle)['active']
    fixture_catalogue(monkeypatch,[]);assert quick(client,vehicle).status_code==409
    assert not get(client,vehicle)['active']
    csrf=client.headers.pop('X-CSRF-Token');assert quick(client,vehicle).status_code==403;client.headers['X-CSRF-Token']=csrf
    with TestClient(app) as other:
        a=other.post('/api/v1/auth/register',json=dict(name='Other',email='stage2d-other@example.test',password='local-password-long')).json();other.headers['X-CSRF-Token']=a['csrf_token']
        assert other.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/quick",json=dict(facts=[],etag=get(client,vehicle)['etag'],request_key=str(uuid4()),confirm=True)).status_code==404
    from test_team import employee,activate
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    _,data=employee(client,['vehicles.view','catalog.view']);low=activate(data)
    try:assert quick(low,vehicle).status_code==403
    finally:low.close()


def test_manual_decisions_pending_is_not_skip_and_past_choices_survive(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Pair'),candidate('Pair',side='left'),candidate('Safe')])
    assert quick(client,vehicle).json()['pending']==2
    p=checked(client,vehicle);generic=next(p for p in p['proposals'] if p['item']['name']=='Pair' and p['item']['installation_position']['side']=='unknown');precise=next(p for p in p['proposals'] if p['item']['name']=='Pair' and p['item']['installation_position']['side']=='left')
    choices={generic['id']:dict(action='skip',reason='Owner chose the precise position'),precise['id']:dict(action='new',reason='Owner verified a distinct physical position')}
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/quick"
    assert client.post(path,json=dict(facts=[],resolutions=choices,etag=get(client,vehicle)['etag'],request_key=str(uuid4()),confirm=True)).status_code==422
    checked_plan=checked(client,vehicle,resolutions=choices)
    r=quick(client,vehicle,resolutions=choices,token=checked_plan['token']);assert r.status_code==200,r.text
    assert get(client,vehicle)['pending_count']==0 and get(client,vehicle)['total']==2
    assert quick(client,vehicle).json()['created']==0
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);assert v.dismantling_v3['skipped'][generic['id']]=='Owner chose the precise position'
        row=db.scalar(select(DismantlingItem).where(DismantlingItem.name=='Pair'));assert row.plan_v3['mapping_reason']=='Owner verified a distinct physical position'


def test_engine_update_adds_only_nonconflicting_new_candidates_and_keeps_history(client,vehicle,monkeypatch):
    items=[candidate('Original safe')];fixture_catalogue(monkeypatch,lambda c:items_with_conditions(items,c))
    assert quick(client,vehicle).status_code==200
    original=get(client,vehicle)['items'][0];assert decision(client,vehicle,[original['id']],'exclude',reason='Keep this owner exclusion').status_code==200
    items.extend([candidate('Свічка розжарювання',tid=next(k for k,v in TYPES.items() if v['name']=='Свічка розжарювання')),candidate('Свічка запалювання',tid=next(k for k,v in TYPES.items() if v['name']=='Свічка запалювання'))])
    r=quick(client,vehicle,facts=[dict(field='powertrain',value='diesel',kind='manual',reference='Owner update',confidence='reported')]);assert r.status_code==200,r.text
    assert r.json()['created']==1 and r.json()['pending']==1
    state=get(client,vehicle);assert any(i['name']=='Свічка розжарювання' and i['inspection']=='unchecked' for i in state['items'])
    assert not next(i for i in state['items'] if i['id']==original['id'])['included']
    assert state['pending_review'][0]['name']=='Свічка запалювання'
    assert quick(client,vehicle).json()['created']==0


def items_with_conditions(items,config):
    result=copy.deepcopy(items)
    for i in result:i['applicability']=assess(i['canonical_part_type_id'],config['values'],configuration=config['values'],provenance=config['provenance'])
    return result


def test_existing_33_29_stocks_30_receipts_sale_archive_and_exclusion_untouched(client,vehicle,monkeypatch):
    from types import SimpleNamespace
    from app.services.dismantling import receipt
    assert client.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start").status_code==200
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id'])
        generated=service.preview(db,v,v.account_id,[],{})['items']
        rows=service.rows_for(db,v);assert len(rows)==33;db.info['actor_id']=v.account_id
        for r in rows[:30]:
            r.status='dismantled';receipt(db,r,SimpleNamespace(quantity=1,condition='used',location='Synthetic fixture',selling_price=None),r.account_id)
            part=db.get(Part,r.part_id);part.selling_price=137;part.unit_cost=17
        rows[32].included=False;old_ids={r.id for r in rows};old_fields={r.id:(r.status,r.included,r.part_id,r.received_at) for r in rows};sold=rows[29].part_id;db.commit()
    assert client.post(f'/api/v1/parts/{sold}/operations',json=dict(type='sale',quantity=1,sale_price='50.00',sale_currency='UAH',request_key=str(uuid4()))).status_code==200
    with Session(engine()) as db:
        db.get(Part,sold).archived=True;db.commit();before=all_tables(db)
        historical={r.id:json.dumps({c.name:str(getattr(r,c.name)) for c in Operation.__table__.columns},sort_keys=True) for r in db.scalars(select(Operation))}
    fixture_catalogue(monkeypatch,generated+[candidate('One safe new type')])
    r=quick(client,vehicle);assert r.status_code==200,r.text
    assert r.json()['created']==1 and r.json()['reused']==33
    assert quick(client,vehicle).json()['created']==0
    state=get(client,vehicle);assert state['total']==34 and state['counts']['in_stock']==29 and state['counts']['received']==30
    assert old_ids<={i['id'] for i in state['items']}
    with Session(engine()) as db:
        after=all_tables(db);assert before['parts']==after['parts'] and before['photos']==after['photos']
        for rid,expected in old_fields.items():
            r=db.get(DismantlingItem,rid);assert (r.status,r.included,r.part_id,r.received_at)==expected
        assert historical=={r.id:json.dumps({c.name:str(getattr(r,c.name)) for c in Operation.__table__.columns},sort_keys=True) for r in db.scalars(select(Operation).where(Operation.id.in_(historical)))}


def test_partial_manual_new_is_saved_as_draft_until_whole_group_safe(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Uncertain pair'),candidate('Uncertain pair',side='left')])
    quick(client,vehicle);p=checked(client,vehicle);first=p['proposals'][0]['id']
    resolution={first:dict(action='new',reason='User inspected one candidate; other still uncertain')}
    p=checked(client,vehicle,resolutions=resolution)
    r=quick(client,vehicle,resolutions=resolution,token=p['token']);assert r.status_code==200,r.text
    assert r.json()['created']==0 and r.json()['pending']==2
    state=get(client,vehicle);assert state['review_drafts'][first]['action']=='new' and state['review_drafts'][first]['reason']==resolution[first]['reason']
    assert quick(client,vehicle).json()['created']==0
    assert get(client,vehicle)['review_drafts']==state['review_drafts']


def test_explicit_distinct_manual_positions_keep_identity_on_automatic_refresh(client,vehicle,monkeypatch):
    fixture_catalogue(monkeypatch,[candidate('Distinct reviewed pair'),candidate('Distinct reviewed pair',side='left')])
    p=checked(client,vehicle);choices={p['id']:dict(action='new',reason='Owner verified a distinct physical constructive position') for p in p['proposals']}
    p=checked(client,vehicle,resolutions=choices);assert quick(client,vehicle,resolutions=choices,token=p['token']).json()['created']==2
    old={i['id'] for i in get(client,vehicle)['items']}
    r=quick(client,vehicle);assert r.status_code==200 and r.json()['created']==r.json()['pending']==0
    assert {i['id'] for i in get(client,vehicle)['items']}==old


def test_manual_snapshot_change_is_rejected_and_other_legacy_ambiguity_is_deferred(client,vehicle,monkeypatch):
    items=[candidate('Pair stale'),candidate('Pair stale',side='left')];fixture_catalogue(monkeypatch,items)
    p=checked(client,vehicle);choices={p['id']:dict(action='skip',reason='Explicit user skip for this preview') for p in p['proposals']}
    p=checked(client,vehicle,resolutions=choices);items.append(candidate('Changed source snapshot'))
    assert quick(client,vehicle,resolutions=choices,token=p['token']).status_code==409
    assert get(client,vehicle)['total']==0 and not get(client,vehicle)['active']
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id'])
        for i in range(2):db.add(DismantlingItem(account_id=v.account_id,vehicle_id=v.id,source='manual',catalog_key=str(i),name='Unclassified legacy '+str(i),category_key='synthetic',category_name='Синтетична конструкція',subcategory_key='local',subcategory_name='Локальний тест',position='',status='unchecked',quantity=1,included=True,plan_v3={}))
        db.commit()
    r=quick(client,vehicle);assert r.status_code==200,r.text
    assert r.json()['created']==0 and r.json()['pending']==3
    assert get(client,vehicle)['total']==2
