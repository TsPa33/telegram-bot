"""Synthetic fixtures; software coverage is never real vehicle catalogue coverage."""
from decimal import Decimal
from copy import deepcopy
import time
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.models import Part,Vehicle,DismantlingItem,Operation
from app.models.canonical import CanonicalType,CanonicalPlacement,CanonicalRun
from app.services.universal_catalogue import prepare,prd_record,evaluate,ReviewedType
from app.services.catalogue_format import digest
from app.services.canonical_jobs import process_one
from tests.test_catalogue_v2 import platform


def source(i=1):return dict(id=i,description='Стартер',normalizeddescription='Електрична деталь',assemblygroupdescription='Електрика',usagedescription='Локальна тестова функція')
def review(row,**kwargs):return dict(source_id=row['id'],source_sha=prd_record(row)['source_sha'],name_uk='Контрольний стартер',category='Електрика та електроніка',subcategory='Стартери та генератори',kind='part',evidence='Explicit synthetic reviewer decision',**kwargs)
def rule(id='fuel',effect='incompatible',**when):return dict(id=id,version=1,when=when or {'fuel_type':['petrol']},effect=effect,priority=1,evidence='Synthetic test specification, not real fitment',explanation='Synthetic constructive restriction')
def config(**values):return dict(values=values,provenance={k:{'confidence':'verified'} for k in values},conflicts=[])


def test_identity_context_no_normalized_name_merge():
    a,b=source(1),source(2);b['description']='Генератор'
    reviews=[review(a),{**review(b),'name_uk':'Контрольний генератор'}]
    result=prepare([a,b,a],reviews)
    assert result['counts']['physical_types']==2 and result['counts']['duplicate_source_rows']==1
    assert len({r['id'] for r in result['types']})==2
    changed={**a,'description':'Інша деталь'}
    assert prepare([changed],reviews[:1])['review'][0]['reason']=='source_changed'
    with pytest.raises(ValueError):prepare([a,changed],reviews)


def test_explicit_link_preserves_id_no_category_rename():
    from app.services.canonical_rules import type_record
    known=type_record('Контрольний стартер','Електрика','Стартери')
    r=review(source())
    assert prepare([source()],[r],[known])['review'][0]['reason']=='explicit_existing_id_required'
    approved=prepare([source()],[{**r,'target_id':known['id']}],[known])['types'][0]
    assert approved['id']==known['id'] and approved['category']=='Електрика'


def test_no_automatic_positions_or_approval():
    assert prepare([source()])['counts']['physical_types']==0
    result=prepare([source()],[review(source())]);assert result['types'][0]['placements']==[]
    assert result['coverage']=='unverified' and result['factory_bom'] is False
    for patch in [dict(category='Unknown'),dict(subcategory='Unknown'),dict(placements=[dict(side='left')])]:
        with pytest.raises(ValueError):ReviewedType.model_validate({**review(source()),**patch})
    r={**review(source()),'kind':'chemical'};assert not prepare([source()],[r])['types']

@pytest.mark.parametrize('fuel,powertrain,transmission,drive',[
 ('petrol','petrol','automatic','AWD'),('diesel','diesel','automatic','FWD'),('petrol','petrol','manual','FWD'),('diesel','diesel','automatic','AWD'),('petrol','PHEV','automatic','AWD'),('electric','BEV','automatic','RWD')])
def test_six_synthetic_constructions_not_real_modifications(fuel,powertrain,transmission,drive):
    c=config(fuel_type=fuel,powertrain=powertrain,transmission=transmission,drive=drive)
    assert evaluate([rule(fuel_type=[fuel],transmission=[transmission],drive=[drive])],c)['status']=='incompatible'
    c['provenance']['fuel_type']['confidence']='reported'
    assert evaluate([rule(fuel_type=[fuel])],c)['status']=='unknown'


def test_conflicting_rules_priorities_and_options():
    c=config(fuel_type='petrol')
    a,b=rule('a'),rule('b',effect='confirmed');b['priority']=100
    assert evaluate([a,b],c)['status']=='unknown'
    assert set(evaluate([a,b],c)['conflicts'])=={'a','b'}
    assert evaluate([a],config())['status']=='unknown'
    c=config(options=[],options_complete=False)
    assert evaluate([rule(options=['SEVEN_SEATS'])],c)['status']=='unknown'
    assert evaluate([rule(fuel_type=['diesel'])],config(fuel_type='petrol'))['status']=='unknown'


def test_tens_of_thousands_without_cost_or_fake_types():
    start=time.monotonic();result=prepare((source(i) for i in range(1,26939)))
    assert result['counts']['source_records']==26938 and result['counts']['review']==26938
    assert result['counts']['physical_types']==0
    print('26938 offline records seconds:',round(time.monotonic()-start,3))


def publish(c,rows,reviews):
    base='/api/v1/catalogue/admin/canonical/universal'
    r=c.post(base+'/preview',json=dict(rows=rows,reviews=reviews,input_sha=digest(rows)));assert r.status_code==202,r.text
    assert process_one(engine())
    p=c.get('/api/v1/catalogue/admin/canonical/runs/'+r.json()['id']).json();assert p['status']=='done',p
    r=c.post(base+'/publish',json=dict(mode='publish',preview_id=p['id'],token=p['token'],confirm=True));assert r.status_code==202,r.text
    assert process_one(engine())
    result=c.get('/api/v1/catalogue/admin/canonical/runs/'+r.json()['id']).json();assert result['status']=='done',result
    return p,result


def test_existing_queue_publication_replay_and_no_inventory(platform,vehicle):
    a=source();p,published=publish(platform,[a],[review(a)])
    r=platform.post('/api/v1/catalogue/admin/canonical/universal/publish',json=dict(mode='publish',preview_id=p['id'],token=p['token'],confirm=True))
    assert r.json()['id']==published['id']
    with Session(engine()) as db:
        t=db.scalar(select(CanonicalType));original=t.id
        assert t.provenance['universal_sources'][0]['original']['id']==1
        assert db.scalar(select(func.count()).select_from(CanonicalPlacement))==1
        assert db.scalar(select(func.count()).select_from(Part))==0
        assert db.scalar(select(func.count()).select_from(DismantlingItem))==0
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==0


def test_unapproved_sources_cannot_publish(logged,platform):
    base='/api/v1/catalogue/admin/canonical/universal';rows=[source()]
    r=platform.post(base+'/preview',json=dict(rows=rows,reviews=[],input_sha=digest(rows)));assert r.status_code==202
    process_one(engine());p=platform.get('/api/v1/catalogue/admin/canonical/runs/'+r.json()['id']).json()
    r=platform.post(base+'/publish',json=dict(mode='publish',preview_id=p['id'],token=p['token'],confirm=True));assert r.status_code==202
    process_one(engine());out=platform.get('/api/v1/catalogue/admin/canonical/runs/'+r.json()['id']).json();assert out['status']=='error'
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(CanonicalType))==0


def test_ordinary_owner_not_platform_and_csrf(logged,vehicle):
    r=logged.post('/api/v1/catalogue/admin/canonical/universal/preview',json=dict(rows=[source()],reviews=[],input_sha=digest([source()])))
    assert r.status_code==403
    with TestClient(__import__('app.main',fromlist=['app']).app) as c:
        c.cookies.update(logged.cookies)
        assert c.post('/api/v1/catalogue/admin/canonical/universal/preview',json=dict(rows=[source()],reviews=[],input_sha=digest([source()]))).status_code==403


def test_prd_identity_cannot_be_rebound_to_second_type():
    from app.services.canonical_rules import type_record
    a=source();old=type_record('Попередній тип','Електрика','Стартери')
    old['provenance']={'universal_sources':[prd_record(a)]}
    report=prepare([a],[review(a)],[old])
    assert report['review'][0]['reason']=='source_rebind_requires_explicit_migration'
    assert not report['types']


def test_rejected_changed_checksum_in_queue(platform):
    rows=[source()]
    r=platform.post('/api/v1/catalogue/admin/canonical/universal/preview',json=dict(rows=rows,reviews=[review(rows[0])],input_sha='0'*64))
    assert r.status_code==202
    assert process_one(engine())
    result=platform.get('/api/v1/catalogue/admin/canonical/runs/'+r.json()['id']).json()
    assert result['status']=='error' and 'checksum' in result['error']
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(CanonicalType))==0


def test_source_alias_id_reuse_preserves_corporate_projection(platform):
    from app.services.canonical_rules import TYPES
    known=next(t for t in TYPES.values() if t['name']=='Стартер')
    a=source();r=review(a);r.update(target_id=known['id'],name_uk='Стартер')
    publish(platform,[a],[r])
    with Session(engine()) as db:
        t=db.get(CanonicalType,known['id'])
        assert t.identity_key==known['identity_key'] and t.name==known['name']
        assert t.provenance['corporate_path']==[r['category'],r['subcategory']]
        assert db.scalar(select(func.count()).select_from(CanonicalType))==1



def test_reviewed_synonyms_reuse_type_and_exact_modification_source_ids(platform,vehicle,monkeypatch):
    from tests.test_unified_catalogue import envelope
    from app.services import unified_catalogue as catalogue
    from app.services.universal_generator import exact_modification_rows
    from app.services.canonical_rules import TYPES
    a,b=source(106),source(107)
    known=next(t for t in TYPES.values() if t['name']=='Стартер')
    publish(platform,[a,b],[{**review(row),'name_uk':'Стартер','target_id':known['id']} for row in (a,b)])
    payload=envelope(car=456,coverage='partial')['payload'];payload.update(schema='carpot.vehicle.plan.v1',manufacturer_id=987,model_id=654)
    payload['categories'][0]['source_prd_sha256']=prd_record(a)['source_sha']
    row=deepcopy(payload['categories'][0]);row['product_id']=107;row['source_prd_sha256']=prd_record(b)['source_sha'];payload['categories'].append(row)
    monkeypatch.setattr(catalogue.CatalogueAdapter,'plan',lambda *a,**k:{'payload':payload})
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.dismantling_v3={'global_selection':dict(car_id=456,model_id=654,manufacturer_id=987,source_snapshot_sha=payload['source_snapshot_sha'],vehicle_basis=catalogue.vehicle_basis(v))}
        result,gaps=exact_modification_rows(v,dict(values={},provenance={},conflicts=[]),db)
        assert len(result)==1 and result[0]['canonical_type_id']==known['id']
        assert result[0]['source_ref_count']==2 and result[0]['source_confirmed']
        assert {r['key'] for r in result[0]['source_refs']}=={'car:456:product:106','car:456:product:107'}
        payload['categories'][0]['source_prd_sha256']='0'*64
        changed,gaps=exact_modification_rows(v,dict(values={},provenance={},conflicts=[]),db)
        assert len(changed)==2 and any('Контрольна сума' in g for g in gaps)
