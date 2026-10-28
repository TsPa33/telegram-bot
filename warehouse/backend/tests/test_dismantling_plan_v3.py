import json,os
import pytest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sqlalchemy import select,text,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import DismantlingItem,Part,Operation,Vehicle
from test_catalogue_v2 import platform,row,plan,upload,confirm
from test_canonical_v3 import market,build,item,fingerprints
from test_dismantling_preview import setup_vehicle,fact

PREFIX=lambda v:f"/api/v1/vehicles/{v['id']}/dismantling-v3"
def preview(c,v,**data):
    r=c.post(PREFIX(v)+'/preview',json={'facts':[],**data});assert r.status_code==200,r.text;return r.json()
def save(c,v,p,**data):return c.post(PREFIX(v)+'/save',json={'facts':[],'token':p['token'],'request_key':str(uuid4()),'confirm':True,**data})
def get(c,v):return c.get(PREFIX(v)).json()
def decision(c,v,ids,action,**kw):return c.post(PREFIX(v)+'/decisions',json={'ids':ids,'action':action,'etag':get(c,v)['etag'],'request_key':str(uuid4()),**kw})

def test_base_explicit_atomic_save_replay_and_no_stock(platform,vehicle):
    setup_vehicle(vehicle)
    with Session(engine()) as db:before=fingerprints(db)
    assert get(platform,vehicle)['total']==0
    p=preview(platform,vehicle);assert p['counts']['new']==33 and not p['counts']['review']
    with Session(engine()) as db:assert fingerprints(db)==before
    key=str(uuid4());r=save(platform,vehicle,p,request_key=key);assert r.status_code==200,r.text
    again=save(platform,vehicle,p,request_key=key);assert again.json()==r.json()
    assert get(platform,vehicle)['total']==33
    assert save(platform,vehicle,p).status_code==409
    fresh=preview(platform,vehicle);assert fresh['counts']['existing']==33
    assert save(platform,vehicle,fresh).status_code==200
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0
    # Legacy prepare no longer creates a parallel base plan for a v3 vehicle.
    assert platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/prepare").json()['created']==0
    assert get(platform,vehicle)['total']==33


def test_legacy_exact_mapping_preserves_exclusion_and_history(platform,vehicle):
    setup_vehicle(vehicle);platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start")
    with Session(engine()) as db:
        r=db.scalar(select(DismantlingItem).limit(1));r.included=False;rid=r.id;db.commit()
    p=preview(platform,vehicle);assert p['counts']['new']==0 and p['counts']['existing']==33
    assert save(platform,vehicle,p).status_code==200
    current=get(platform,vehicle);assert current['total']==33
    old=next(i for i in current['items'] if i['id']==rid);assert not old['included']


def test_states_bulk_exclusion_restore_receipt_and_sold_protection(platform,vehicle):
    setup_vehicle(vehicle);assert save(platform,vehicle,preview(platform,vehicle)).status_code==200
    ids=[i['id'] for i in get(platform,vehicle)['items'][:3]]
    assert decision(platform,vehicle,ids,'exclude',reason='Немає за комплектацією').status_code==200
    assert get(platform,vehicle)['counts']['excluded']==3
    assert decision(platform,vehicle,ids,'restore').status_code==200
    assert decision(platform,vehicle,[ids[0]],'receipt',confirm=True).status_code==409
    assert decision(platform,vehicle,ids,'present').status_code==200
    assert decision(platform,vehicle,ids,'dismantled',confirm=True).status_code==200
    assert decision(platform,vehicle,[ids[0]],'receipt',confirm=True,quantity=2).status_code==200
    assert decision(platform,vehicle,[ids[0]],'receipt',confirm=True,quantity=2).json()['updated']==0
    current=get(platform,vehicle);stock=next(i for i in current['items'] if i['id']==ids[0])
    assert stock['operational_state']=='received'
    assert decision(platform,vehicle,ids,'exclude',reason='Must rollback entire batch').status_code==409
    assert get(platform,vehicle)['counts']['excluded']==0
    sale=platform.post(f"/api/v1/parts/{stock['part_id']}/operations",json={'type':'sale','quantity':2,'sale_price':'17.00','sale_currency':'USD','request_key':str(uuid4())});assert sale.status_code==200,sale.text
    assert next(i for i in get(platform,vehicle)['items'] if i['id']==ids[0])['operational_state']=='sold'
    assert decision(platform,vehicle,[ids[0]],'not_applicable',reason='Cannot remove sold history').status_code==409


def test_stale_requests_archived_workspace_and_bad_input(platform,vehicle):
    from fastapi.testclient import TestClient
    from app.main import app
    from conftest import signup
    setup_vehicle(vehicle);p=preview(platform,vehicle)
    with Session(engine()) as db:db.get(Vehicle,vehicle['id']).engine='D4204T14';db.commit()
    assert save(platform,vehicle,p).status_code==409
    p=preview(platform,vehicle);assert save(platform,vehicle,p).status_code==200
    old=get(platform,vehicle);rid=old['items'][0]['id']
    assert decision(platform,vehicle,[rid],'present').status_code==200
    assert decision(platform,vehicle,[rid],'absent',reason='changed',etag=old['etag']).status_code==409
    assert decision(platform,vehicle,[rid,rid],'exclude',reason='duplicate').status_code==422
    assert decision(platform,vehicle,[rid],'absent').status_code==422
    with TestClient(app) as other:
        signup(other,'plan-other@example.test');assert other.get(PREFIX(vehicle)).status_code==404
        assert other.post(PREFIX(vehicle)+'/preview',json={'facts':[]}).status_code==404
    with Session(engine()) as db:db.get(Vehicle,vehicle['id']).archived=True;db.commit()
    assert decision(platform,vehicle,[rid],'present').status_code==404
    assert platform.get(PREFIX(vehicle)).status_code==200


def test_concurrent_save_and_decisions(platform,vehicle):
    setup_vehicle(vehicle);p=preview(platform,vehicle);key=str(uuid4())
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:save(platform,vehicle,p,request_key=key),range(2)))
    assert all(r.status_code==200 for r in results)
    current=get(platform,vehicle);rid=current['items'][0]['id']
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda action:decision(platform,vehicle,[rid],action,etag=current['etag'],reason='Concurrent inspection'),['present','absent']))
    assert sorted(r.status_code for r in results)==[200,409]


def test_catalogue_update_is_explicit_and_preserves_decisions(platform,vehicle):
    setup_vehicle(vehicle);assert save(platform,vehicle,preview(platform,vehicle)).status_code==200
    first=get(platform,vehicle);rid=first['items'][0]['id'];decision(platform,vehicle,[rid],'exclude',reason='Keep owner decision')
    market(platform,[item('one')]);build(platform)
    assert get(platform,vehicle)['total']==33 and not next(i for i in get(platform,vehicle)['items'] if i['id']==rid)['included']
    p=preview(platform,vehicle);assert p['counts']['review']==0
    assert p['differences']
    assert save(platform,vehicle,p).status_code==200
    assert get(platform,vehicle)['total']==33 and not next(i for i in get(platform,vehicle)['items'] if i['id']==rid)['included']


def test_ambiguous_legacy_requires_manual_one_to_one(platform,vehicle):
    setup_vehicle(vehicle);platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start")
    with Session(engine()) as db:
        original=db.scalar(select(DismantlingItem).where(DismantlingItem.name=='Генератор'))
        copy={k:v for k,v in original.__dict__.items() if not k.startswith('_') and k not in ('id','created_at')};copy['source']='manual-legacy';copy['catalog_key']='other-generator';db.add(DismantlingItem(**copy));db.commit()
    p=preview(platform,vehicle);review=next(x for x in p['proposals'] if x['action']=='review')
    assert save(platform,vehicle,p).status_code==409
    resolutions={review['id']:{'action':'link','item_id':review['candidates'][0]['id'],'reason':'Inspected same constructive position'}}
    p=preview(platform,vehicle,resolutions=resolutions);assert not p['counts']['review']
    assert save(platform,vehicle,p,resolutions=resolutions).status_code==200
    assert get(platform,vehicle)['total']==34 # Preserves historical duplicate; creates none.


def test_explicit_refinement_reuses_bound_item_and_preserves_decision(platform,vehicle):
    setup_vehicle(vehicle);assert save(platform,vehicle,preview(platform,vehicle)).status_code==200
    original=next(i for i in get(platform,vehicle)['items'] if i['name']=='Зовнішнє дзеркало' and 'ліва' in i['position'])
    decision(platform,vehicle,[original['id']],'exclude',reason='Owner decision before refinement')
    market(platform,[row('mirror',part_name='Зовнішнє дзеркало переднє ліве Volvo XC40',category='Кузов',subcategory='Дзеркала',side='',position='')]);build(platform)
    p=preview(platform,vehicle);new=next(i for i in p['proposals'] if i['action']=='review' and i['item']['name']=='Зовнішнє дзеркало')
    assert save(platform,vehicle,p).status_code==409
    resolutions={original['placement_id']:{'action':'skip','reason':'Refined existing generic position'},new['id']:{'action':'link','item_id':original['id'],'reason':'Inspected same physical left exterior mirror'}}
    p=preview(platform,vehicle,resolutions=resolutions);assert not p['counts']['review']
    assert save(platform,vehicle,p,resolutions=resolutions).status_code==200
    current=get(platform,vehicle);assert current['total']==33
    refined=next(i for i in current['items'] if i['id']==original['id']);assert not refined['included'] and refined['placement_id']==new['id']
    assert preview(platform,vehicle)['counts']['review']==0


def test_read_only_user_cannot_save_or_decide(platform,vehicle,monkeypatch):
    from test_team import employee,activate
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true');setup_vehicle(vehicle)
    _,data=employee(platform,['vehicles.view','catalog.view']);c=activate(data)
    try:
        p=preview(c,vehicle)
        assert save(c,vehicle,p).status_code==403
        assert c.post(PREFIX(vehicle)+'/decisions',json={'ids':['x'],'action':'present','etag':'a'*64,'request_key':str(uuid4())}).status_code==403
    finally:c.close()


def test_source_price_and_new_model_do_not_mutate_saved_plan(platform,vehicle):
    setup_vehicle(vehicle);market(platform,[item('first')]);build(platform)
    p=preview(platform,vehicle);assert save(platform,vehicle,p).status_code==200
    before=get(platform,vehicle)
    market(platform,[item('second',model='XC90')]);build(platform)
    assert get(platform,vehicle)['items']==before['items'] and get(platform,vehicle)['revision']==before['revision']
    assert get(platform,vehicle)['catalogue_changed']
    diff=preview(platform,vehicle);assert diff['counts']['new']==0


def test_real_A_xc90_plan_and_multiple_donors(platform,vehicle,tmp_path):
    from app.services.aleto_import import BUNDLED_PACKAGE
    j=plan(platform,upload(platform,raw=BUNDLED_PACKAGE.read_bytes(),filename=BUNDLED_PACKAGE.name))
    if j['report']['issues']:j=plan(platform,j,{i['key']:{'action':'skip'} for i in j['report']['issues']})
    confirm(platform,j);build(platform);setup_vehicle(vehicle)
    with Session(engine()) as db:db.get(Vehicle,vehicle['id']).model='XC90';db.commit()
    reports=[]
    for fuel in ('petrol','diesel'):
        facts=[fact('powertrain',fuel)]
        p=preview(platform,vehicle,facts=facts)
        # Human-equivalent fixture: omit broad/precise ambiguities, never mass approve.
        resolutions={i['id']:{'action':'skip','reason':'Fixture leaves physical ambiguity unresolved; not approved'} for i in p['proposals'] if i['action']=='review'}
        p=preview(platform,vehicle,facts=facts,resolutions=resolutions)
        assert not p['counts']['review']
        r=save(platform,vehicle,p,facts=facts,resolutions=resolutions);assert r.status_code==200,r.text
        reports.append({'powertrain':fuel,'counts':p['counts'],'saved_total':get(platform,vehicle)['total'],'configuration_changes':p['configuration_changes']})
    second=platform.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2020,'donor_id':'SECOND-XC90','acquisition_date':'2026-01-01','acquisition_cost':'0'}).json()
    assert get(platform,second)['total']==0
    assert get(platform,vehicle)['total']>33
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0
    Path(os.environ.get('WAREHOUSE_MANAGED_PLAN_REPORT',str(tmp_path/'xc90-plan.json'))).write_text(json.dumps({'dataset':'real Volvo A; synthetic XC90 donor and unverified trial engine facts','real_B_tested':False,'runs':reports,'no_stock_created':True},ensure_ascii=False,indent=2)+'\n')


def test_legacy_stock_prices_reservations_and_bypass_protection(platform,vehicle):
    setup_vehicle(vehicle);platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start")
    with Session(engine()) as db:rid=db.scalar(select(DismantlingItem.id).where(DismantlingItem.name=='Генератор'))
    path=f"/api/v1/vehicles/{vehicle['id']}/dismantling"
    assert platform.post(path+'/actions',json={'ids':[rid],'action':'dismantled'}).status_code==200
    r=platform.post(path+'/actions',json={'ids':[rid],'action':'receipt','selling_price':'123.45','quantity':2});assert r.status_code==200,r.text
    with Session(engine()) as db:
        row=db.get(DismantlingItem,rid);pid=row.part_id;before=db.get(Part,pid).selling_price
    assert platform.post(f'/api/v1/parts/{pid}/operations',json={'type':'reserve','quantity':1,'reason':'Existing reservation'}).status_code==200
    p=preview(platform,vehicle);assert p['counts']['with_stock_history']==1
    assert save(platform,vehicle,p).status_code==200
    assert decision(platform,vehicle,[rid],'exclude',reason='Cannot exclude reserved receipt').status_code==409
    assert platform.post(path+'/plan',json={'ids':[rid],'included':False}).status_code==409
    with Session(engine()) as db:
        assert db.get(Part,pid).selling_price==before
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1
    unchecked=next(i for i in get(platform,vehicle)['items'] if not i['protected'])
    assert platform.post(path+'/actions',json={'ids':[unchecked['id']],'action':'dismantled'}).status_code==409
    assert platform.post(path+'/actions',json={'ids':[unchecked['id']],'action':'receipt'}).status_code==409


def test_additive_migration_on_populated_legacy_db(platform,vehicle,part):
    import subprocess,sys
    setup_vehicle(vehicle);platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start")
    with Session(engine()) as db:
        db.scalar(select(DismantlingItem).limit(1)).included=False;db.commit()
        before={t:list(db.execute(text(sql)).mappings()) for t,sql in {'parts':'SELECT id,quantity,selling_price,unit_cost FROM parts ORDER BY id','items':'SELECT id,source,catalog_key,included,status FROM dismantling_items ORDER BY id','ops':'SELECT * FROM operations ORDER BY id'}.items()}
    try:
        subprocess.run([sys.executable,'-m','alembic','downgrade','76af12de4b90'],check=True,capture_output=True)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)
        with Session(engine()) as db:
            for t,sql in {'parts':'SELECT id,quantity,selling_price,unit_cost FROM parts ORDER BY id','items':'SELECT id,source,catalog_key,included,status FROM dismantling_items ORDER BY id','ops':'SELECT * FROM operations ORDER BY id'}.items():assert before[t]==list(db.execute(text(sql)).mappings())
    finally:subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)


def test_failure_rolls_back_plan_and_receipt_batches(platform,vehicle,monkeypatch):
    setup_vehicle(vehicle);p=preview(platform,vehicle)
    with Session(engine()) as db:before=fingerprints(db)
    import app.services.dismantling_plan_v3 as service
    original=service.record
    def fail(*args,**kwargs):
        original(*args,**kwargs);raise RuntimeError('Injected atomic plan failure')
    monkeypatch.setattr(service,'record',fail)
    with pytest.raises(RuntimeError):save(platform,vehicle,p)
    with Session(engine()) as db:assert fingerprints(db)==before
    monkeypatch.setattr(service,'record',original)
    assert save(platform,vehicle,p).status_code==200
    ids=[i['id'] for i in get(platform,vehicle)['items'][:2]]
    decision(platform,vehicle,ids,'present');decision(platform,vehicle,ids,'dismantled',confirm=True)
    with Session(engine()) as db:before=fingerprints(db)
    import app.services.dismantling as legacy
    original_receipt=legacy.receipt;calls=[]
    def receipt(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise RuntimeError('Injected second receipt failure')
        return original_receipt(*args,**kwargs)
    monkeypatch.setattr(legacy,'receipt',receipt)
    with pytest.raises(RuntimeError):decision(platform,vehicle,ids,'receipt',confirm=True)
    with Session(engine()) as db:assert fingerprints(db)==before


def test_explicit_new_position_after_refinement_does_not_reuse_legacy_key(platform,vehicle):
    setup_vehicle(vehicle);assert save(platform,vehicle,preview(platform,vehicle)).status_code==200
    original=next(i for i in get(platform,vehicle)['items'] if i['name']=='Зовнішнє дзеркало' and 'ліва' in i['position'])
    market(platform,[row('mirror',part_name='Зовнішнє дзеркало переднє ліве Volvo XC40',category='Кузов',subcategory='Дзеркала',side='',position='')]);build(platform)
    p=preview(platform,vehicle);precise=next(x for x in p['proposals'] if x['action']=='review' and x['item']['name']=='Зовнішнє дзеркало')
    resolutions={original['placement_id']:{'action':'skip','reason':'Refining same position'},precise['id']:{'action':'link','item_id':original['id'],'reason':'Reviewed physical identity'}}
    p=preview(platform,vehicle,resolutions=resolutions);assert save(platform,vehicle,p,resolutions=resolutions).status_code==200
    resolutions={original['placement_id']:{'action':'new','reason':'Explicitly inspected a distinct second constructive position'}}
    p=preview(platform,vehicle,resolutions=resolutions);assert not p['counts']['review']
    r=save(platform,vehicle,p,resolutions=resolutions);assert r.status_code==200,r.text
    assert get(platform,vehicle)['total']==34


def test_catalogue_busy_returns_controlled_conflict_without_wait_or_write(platform,vehicle):
    from app.services.catalogue_import import LOCK
    setup_vehicle(vehicle);p=preview(platform,vehicle)
    with engine().begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':LOCK})
        r=save(platform,vehicle,p);assert r.status_code==409 and 'Каталог' in r.json()['detail']
        assert get(platform,vehicle)['total']==0
    assert save(platform,vehicle,p).status_code==200


def test_trial_configuration_survives_reload_and_catalogue_checks(platform,vehicle):
    setup_vehicle(vehicle)
    facts=[fact('powertrain','petrol'),fact('engine_code','B4204T23')]
    p=preview(platform,vehicle,facts=facts);assert save(platform,vehicle,p,facts=facts).status_code==200
    fresh=preview(platform,vehicle);assert fresh['configuration']['values']['powertrain']=='petrol' and fresh['configuration']['values']['engine_code']=='B4204T23'
    assert fresh['configuration_changes']=={}
    assert save(platform,vehicle,fresh).status_code==200
    assert get(platform,vehicle)['configuration']['values']['powertrain']=='petrol'
    cleared=preview(platform,vehicle,reset_trial=True);assert cleared['configuration']['values']['engine_code'] is None
    assert 'engine_code' in cleared['configuration_changes']
    with Session(engine()) as db:db.get(Vehicle,vehicle['id']).engine='D4204T14';db.commit()
    assert get(platform,vehicle)['configuration_stale']
    changed=preview(platform,vehicle);assert changed['configuration']['values']['engine_code']=='D4204T14'
    assert get(platform,vehicle)['configuration']['values']['engine_code']=='B4204T23'


def test_incomplete_legacy_sale_history_does_not_claim_sold(platform,vehicle):
    setup_vehicle(vehicle);assert save(platform,vehicle,preview(platform,vehicle)).status_code==200
    rid=get(platform,vehicle)['items'][0]['id'];decision(platform,vehicle,[rid],'present');decision(platform,vehicle,[rid],'dismantled',confirm=True);decision(platform,vehicle,[rid],'receipt',confirm=True,quantity=2)
    with Session(engine()) as db:
        r=db.get(DismantlingItem,rid);p=db.get(Part,r.part_id);p.quantity=0
        db.add(Operation(account_id=r.account_id,actor_id=r.account_id,vehicle_id=r.vehicle_id,part_id=p.id,entity_id=p.id,entity_type='parts',type='sale',reason='Incomplete legacy fixture',before={'quantity':2},after={}))
        db.commit()
    current=next(i for i in get(platform,vehicle)['items'] if i['id']==rid)
    assert current['operational_state']=='received' and current['protected']
