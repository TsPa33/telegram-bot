"""Stage 2C: observable activation, explicit publication, immutable populated legacy stock."""
import json,os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text,func
from sqlalchemy.orm import Session
from app.db import engine
from app.main import app
from app.models import Vehicle,DismantlingItem,Part,Operation,now
from app.models.canonical import CanonicalRun,CanonicalState
from app.services.canonical_jobs import process_one
from app.services.canonical_rules import TYPES,UNIVERSAL_TYPES,classify,placement
from app.services.canonical_catalogue import constructive_inputs
from app.services.canonical_diagnostics import diagnostics
from test_catalogue_v2 import platform,row,plan,upload,confirm,BUNDLED_PACKAGE
from test_canonical_v3 import market,build,item,fingerprints,PREFIX
from test_dismantling_plan_v3 import preview,save,get,decision
from test_dismantling_preview import setup_vehicle,save_config,run
from test_v3_release_audit import all_tables


def test_unpublished_diagnostics_is_readonly_and_proves_33_fallback(platform,vehicle):
    setup_vehicle(vehicle);market(platform,[item()])
    with Session(engine()) as db:before=all_tables(db)
    r=platform.get(PREFIX+'/diagnostics',params={'vehicle_id':vehicle['id']});assert r.status_code==200,r.text
    d=r.json();assert d['catalogue_v2']==dict(offers=1,paths=1,models=1)
    assert d['canonical']['published'] is False and d['canonical']['snapshot_sha'] is None
    assert d['vehicle']['candidates']==33 and d['vehicle']['fallback_used']
    assert preview(platform,vehicle)['catalogue_status']==dict(published=False,fallback_used=True)
    with Session(engine()) as db:assert all_tables(db)==before


def test_universal_templates_no_fuzzy_oem_counts_or_brand_specific_function(platform,vehicle):
    assert len(UNIVERSAL_TYPES)>200
    for source in constructive_inputs():
        c=classify(source);assert c['type_id'] and c['quality']=='verified_rule'
        assert source['oem'] is None and source['manufacturer']=='' and source['model']==''
        assert c['installation']==dict(side='unknown',position='unknown',mount=[])
    assert not classify(dict(key='x',sha='',title='Насос довільний невідомий',category='Силовий агрегат')).get('type_id')
    market(platform,[item()]);build(platform)
    for brand,model in [('Volvo','XC60'),('BMW','X3'),('Audi','Q5')]:
        r=platform.get('/api/v1/catalogue/canonical/candidates',params={'manufacturer':brand,'model':model,'limit':200}).json()
        assert r['total']>200 and r['published']
    setup_vehicle(vehicle);p=run(platform,vehicle).json()
    assert p['total']>200 and not p['fallback_used'] and p['status_counts']['confirmed']==0
    assert all(i['quantity'] is None for i in p['items'])


def test_xc60_legacy_33_29_parts_30_history_survive_publish_and_safe_update(platform,vehicle):
    setup_vehicle(vehicle)
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.model='XC60';v.year=2018;db.commit()
    assert platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start").status_code==200
    from app.services.dismantling import receipt
    with Session(engine()) as db:
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==vehicle['id']).order_by(DismantlingItem.id)))
        assert len(rows)==33
        db.info['actor_id']=rows[0].account_id
        for r in rows[:30]:
            r.status='dismantled';assert receipt(db,r,SimpleNamespace(quantity=1,condition='used',location='Local Stage2C fixture',selling_price=None),r.account_id)
            part=db.get(Part,r.part_id);part.selling_price=137;part.unit_cost=17
        rows[32].included=False
        old_ids={r.id for r in rows};old_rows={r.id:(r.included,r.received_at,r.part_id,r.status) for r in rows};sold_part=rows[29].part_id;db.commit()
    assert platform.post(f'/api/v1/parts/{sold_part}/operations',json=dict(type='sale',quantity=1,sale_price='50.00',sale_currency='UAH',request_key=str(uuid4()))).status_code==200
    with Session(engine()) as db:
        before=all_tables(db)
        historical_ids=set(db.scalars(select(Operation.id)))
        historical={r.id:json.dumps({c.name:str(getattr(r,c.name)) for c in Operation.__table__.columns},sort_keys=True) for r in db.scalars(select(Operation).where(Operation.id.in_(historical_ids)))}
    market(platform,[row('xc60-generator',manufacturer='Volvo',model='XC60',part_name='Генератор',category='Електрика',subcategory='Генератори',side='',position='')])
    with Session(engine()) as db:before_publish=all_tables(db)
    result=build(platform)
    with Session(engine()) as db:
        after_publish=all_tables(db)
        assert all(before_publish[k]==after_publish[k] for k in before_publish if not k.startswith('canonical_'))
    p=preview(platform,vehicle);assert p['counts']['existing']==33 and p['counts']['new']>150 and p['counts']['with_stock_history']==30
    assert p['counts']['review']==0,p['counts']
    r=save(platform,vehicle,p);assert r.status_code==200,r.text
    again=preview(platform,vehicle);assert again['counts']['new']==again['counts']['review']==0
    assert save(platform,vehicle,again).status_code==200
    current=get(platform,vehicle);assert current['counts']['in_stock']==29 and current['counts']['received']==30
    assert len({i['id'] for i in current['items']})==current['total']>200
    assert old_ids<={i['id'] for i in current['items']}
    with Session(engine()) as db:
        for rid,expected in old_rows.items():
            r=db.get(DismantlingItem,rid);assert (r.included,r.received_at,r.part_id,r.status)==expected
        after=all_tables(db);assert before['parts']==after['parts'] and before['photos']==after['photos']
        # New bind audit is expected; all historical events remain byte-identical.
        assert db.scalar(select(func.count()).select_from(Part).where(Part.quantity>0))==29
        assert db.scalar(select(func.count()).select_from(Part))==30
        assert historical=={r.id:json.dumps({c.name:str(getattr(r,c.name)) for c in Operation.__table__.columns},sort_keys=True) for r in db.scalars(select(Operation).where(Operation.id.in_(historical_ids)))}
        historic=list(db.scalars(select(Operation).where(Operation.type.in_(['receipt','dismantling_receipt']))));assert len(historic)>=60
    ids=[i['id'] for i in current['items'] if i['placement_id'] and not i['protected']][:20]
    assert decision(platform,vehicle,ids,'exclude',reason='Stage2C physical test exclusion').status_code==200
    assert decision(platform,vehicle,ids,'restore').status_code==200
    with Session(engine()) as db:assert all_tables(db)['parts']==before['parts']
    with TestClient(app) as other:
        u=other.post('/api/v1/auth/register',json=dict(name='Other warehouse',email='stage2c-other@example.test',password='long-local-password')).json()
        other.headers['X-CSRF-Token']=u['csrf_token']
        assert other.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3").status_code==404
        assert other.get(PREFIX+'/diagnostics').status_code==403


@pytest.mark.parametrize('powertrain',['petrol','diesel','HEV','PHEV','BEV'])
def test_engine_conditions_do_not_claim_presence(platform,vehicle,powertrain):
    setup_vehicle(vehicle);build(platform)
    save_config(platform,vehicle,dict(manufacturer='Volvo',model='XC40',year=2020,powertrain=powertrain,drive='FWD'))
    p=run(platform,vehicle).json();assert p['status_counts']['confirmed']==0
    electric=next(i for i in p['items'] if i['name']=='Тягова батарея')
    assert electric['applicability_status']==('incompatible' if powertrain in ('petrol','diesel') else 'unknown')
    assert next(i for i in p['items'] if i['name']=='Карданний вал')['applicability_status']=='incompatible'
    assert next(i for i in p['items'] if i['name']=='Компресор пневмопідвіски')['applicability_status']=='unknown'


def test_diagnostics_fail_closed_and_csrf_and_stale_snapshot(platform,vehicle,monkeypatch):
    setup_vehicle(vehicle);p=build(platform,False)
    # A different source set invalidates publication even with the old token.
    market(platform,[item('changed')])
    r=platform.post(PREFIX+'/runs',json=dict(mode='publish',preview_id=p['id'],token=p['token'],confirm=True));assert r.status_code==202
    process_one(engine());done=platform.get(PREFIX+'/runs/'+r.json()['id']).json();assert done['status']=='error'
    assert not platform.get(PREFIX+'/diagnostics').json()['canonical']['published']
    csrf=platform.headers.pop('X-CSRF-Token');assert platform.post(PREFIX+'/runs',json={'mode':'preview'}).status_code==403;platform.headers['X-CSRF-Token']=csrf
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',raising=False)
    assert platform.get(PREFIX+'/diagnostics').status_code==403
    assert platform.get(PREFIX+'/types').status_code==403
    assert platform.post(PREFIX+'/runs',json={'mode':'preview'}).status_code==403


def test_real_A_readonly_activation_evidence(platform,vehicle,tmp_path):
    setup_vehicle(vehicle)
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.model='XC60';v.year=2018;db.commit()
    j=plan(platform,upload(platform,raw=BUNDLED_PACKAGE.read_bytes(),filename=BUNDLED_PACKAGE.name))
    if j['report']['issues']:j=plan(platform,j,{i['key']:{'action':'skip'} for i in j['report']['issues']})
    confirm(platform,j)
    before=platform.get(PREFIX+'/diagnostics',params={'vehicle_id':vehicle['id']}).json()
    report=build(platform)['report']
    after=platform.get(PREFIX+'/diagnostics',params={'vehicle_id':vehicle['id']}).json()
    report={k:v for k,v in report.items() if k!='issues'}
    evidence=dict(real_A=True,real_B_tested=False,before=before,normalization=report,after=after)
    dest=Path(os.environ.get('WAREHOUSE_STAGE2C_EVIDENCE',str(tmp_path/'real-A.json')));dest.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    assert before['vehicle']['candidates']==33 and before['vehicle']['fallback_used']
    assert after['vehicle']['candidates']>200 and not after['vehicle']['fallback_used']
    assert after['catalogue_v2']['offers']==7246
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0


def test_two_same_model_donors_share_functions_but_never_plan_rows(platform,vehicle):
    setup_vehicle(vehicle);build(platform)
    other=platform.post('/api/v1/vehicles',json=dict(manufacturer='Volvo',model='XC40',year=2018,donor_id='STAGE2C-SECOND-DONOR',acquisition_date='2026-01-01',acquisition_cost='0')).json()
    first=preview(platform,vehicle);second=preview(platform,other)
    assert first['counts']['proposed']==second['counts']['proposed']>200
    assert save(platform,other,first).status_code==409
    assert save(platform,vehicle,first).status_code==200
    assert save(platform,other,second).status_code==200
    a=get(platform,vehicle);b=get(platform,other)
    assert {i['id'] for i in a['items']}.isdisjoint({i['id'] for i in b['items']})
    assert {i['placement_id'] for i in a['items']}=={i['placement_id'] for i in b['items']}
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Part))==0


def test_rear_view_camera_requires_explicit_rear_position():
    def match(title):return classify(dict(key='camera-regression',sha='',title=title,category='Електрика',subcategory='Системи допомоги водію'))
    for title in ['Камера огляду','Камера переднього огляду','Камера переднього заднього огляду']:
        assert not match(title).get('type_id')
    r=match('Камера заднього огляду');assert r['quality']=='verified_rule' and r['installation']['position']=='rear'


def test_group_review_keeps_new_rear_camera_condition(platform):
    market(platform,[row(str(i),part_name=title,category='Електрика',subcategory='Системи допомоги водію',side='',position='') for i,title in enumerate(['Камера огляду','Камера переднього огляду','Камера заднього огляду'])])
    from app.services.canonical_review import effective_conditions
    tid=next(tid for tid,t in TYPES.items() if t['name']=='Камера заднього огляду')
    draft=dict(type_id=tid,phrase='камера огляду',category='Електрика',subcategory='Системи допомоги водію',evidence='Local test: enforce explicit rear installation',conditions={})
    conditions=effective_conditions(draft);assert conditions['position_known'] and conditions['forbidden_positions']==['front','unknown']
    r=platform.post(PREFIX+'/rules/preview',json=draft);assert r.status_code==202,r.text
    process_one(engine());report=platform.get(PREFIX+'/runs/'+r.json()['id']).json()['report']
    assert report['matched_count']==1 and report['exception_count']==2 and report['conflict_count']==0
    done=platform.get(PREFIX+'/runs/'+r.json()['id']).json()
    approved=platform.post(PREFIX+'/rules/approve',json=dict(preview_id=done['id'],token=done['token'],confirm=True));assert approved.status_code==202
    process_one(engine());assert platform.get(PREFIX+'/runs/'+approved.json()['id']).json()['status']=='done'
    build(platform)
    cameras=platform.get('/api/v1/catalogue/canonical/candidates',params=dict(manufacturer='Volvo',model='XC40')).json()['items']
    assert {c['placement']['position'] for c in cameras if c['name']=='Камера заднього огляду'}=={'unknown','rear'}
