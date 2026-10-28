"""Verified coverage, exact grouped approval, VIN-ready facts safety."""
import pytest
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.db import engine
from app.models.canonical import CanonicalAlias,CanonicalState
from app.services.canonical_rules import classify,TYPES
from app.services.canonical_applicability import assess
from app.services.canonical_jobs import process_one
from test_catalogue_v2 import platform,row
from test_canonical_v3 import market,build,PREFIX,fingerprints

def result(title,**kw):
    return classify(dict(title=title,category='Двигун',subcategory='',manufacturer='Volvo',model='XC40',key='x',sha='a',**kw))

@pytest.mark.parametrize('brand,model',[('Volvo','XC40'),('BMW','X3'),('Audi','Q5')])
def test_universal_function_not_brand(brand,model):
    a=classify(dict(title=f'Генератор {brand} {model}',manufacturer=brand,model=model,category='Електрика',key='a',sha='a'))
    assert a['type_id']==result('Генератор')['type_id']

@pytest.mark.parametrize('a,b',[('Датчик тиску пального','Датчик тиску в шинах'),('Блок управління двигуном','Блок управління коробкою передач')])
def test_similar_labels_distinct_functions(a,b):
    x=result(a);y=classify(dict(title=b,category='Електрика',subcategory='',key='y',sha='b'))
    assert x.get('type_id') and y.get('type_id') and x['type_id']!=y['type_id']

def test_fuel_and_exact_code_preserved_without_fitment_inference():
    a=result('Форсунка дизельна Volvo XC40 D4204T14');b=result('Форсунка бензинова Volvo XC40 B4204T23')
    assert a['type_id']==b['type_id']
    assert a['features']['engine_codes']==['D4204T14']
    assert a['features']['fuel_labels']==['diesel']
    for powertrain in ('HEV','PHEV','BEV'):
        report=assess(a['type_id'],{'powertrain':powertrain},a['features'])
        assert 'B' in report['groups'] and 'E' in report['groups'] and not report['confirms_fitment']
    assert result('Форсунка')['quality'] in ('review','unprocessed') # No fuel subsystem context is supplied by default below.

@pytest.mark.parametrize('title',['Комп','Блок','Насос','Датчик тиску','Генератор імпульсів'])
def test_incomplete_never_fuzzy(title):assert not result(title).get('type_id')

def operation(c,path,payload):
    r=c.post(PREFIX+path,json=payload);assert r.status_code==202,r.text
    process_one(engine());return c.get(PREFIX+'/runs/'+r.json()['id']).json()

def test_group_preview_approval_is_explicit_audited_and_not_publication(platform):
    market(platform,[row(str(i),part_name='Клапан контрольний Volvo XC40',category='Двигун',subcategory='Клапани',side='',position='') for i in range(4)])
    tid=platform.post(PREFIX+'/types',json={'name':'Контрольний клапан','category':'Двигун','subcategory':'Клапани','evidence':'Inspected functional identity'}).json()['id']
    groups=platform.get(PREFIX+'/groups').json();assert groups['items'][0]['offers']==4
    preview=operation(platform,'/rules/preview',{'type_id':tid,'phrase':'клапан контрольний','category':'Двигун','subcategory':'Клапани','evidence':'All source records inspected'})
    assert preview['status']=='done',preview
    assert preview['report']['will_link_count']==4 and preview['report']['all_members_checked']
    assert preview['report']['conflict_count']==0
    assert platform.post(PREFIX+'/rules/approve',json={'preview_id':preview['id'],'token':preview['token'],'confirm':False}).status_code==422
    done=operation(platform,'/rules/approve',{'preview_id':preview['id'],'token':preview['token'],'confirm':True})
    assert done['status']=='done',done
    with Session(engine()) as db:
        assert db.get(CanonicalState,1).snapshot_sha is None
        alias=db.scalar(select(CanonicalAlias));assert alias.actor_id and alias.revision==1
    report=build(platform)['report'];assert report['mapped_offers']==4


def test_group_conditions_exceptions_and_ambiguous_rejection(platform):
    market(platform,[row('d',part_name='Клапан контрольний дизельний Volvo XC40',category='Двигун',subcategory='Клапани',side='',position=''),row('p',part_name='Клапан контрольний бензиновий Volvo XC40',category='Двигун',subcategory='Клапани',side='',position='')])
    tid=platform.post(PREFIX+'/types',json={'name':'Контрольний клапан','category':'Двигун','subcategory':'Клапани','evidence':'Inspected source records'}).json()['id']
    p=operation(platform,'/rules/preview',{'type_id':tid,'phrase':'клапан контрольний','category':'Двигун','subcategory':'Клапани','conditions':{'fuel_labels':['diesel']},'evidence':'Reviewed diesel context'})
    assert p['status']=='done',p
    assert p['report']['matched_count']==1 and p['report']['exception_count']==1
    bad=operation(platform,'/rules/preview',{'type_id':tid,'phrase':'Комп','category':'Двигун','subcategory':'Клапани','evidence':'Insufficient generic name'})
    assert bad['status']=='error'


def test_configuration_explicit_provenance_no_legacy_writes(platform,vehicle):
    path=f"/api/v1/vehicles/{vehicle['id']}/configuration"
    with Session(engine()) as db:before={k:v for k,v in fingerprints(db).items() if k!='vehicle_configurations'}
    facts=[{'field':'engine_code','value':'D4204T14','kind':'manual','reference':'Engine plate inspected','confidence':'verified'}, {'field':'powertrain','value':'diesel','kind':'manual','reference':'Engine plate inspected','confidence':'verified'}]
    p=platform.post(path+'/preview',json={'facts':facts}).json();assert p['status']=='preview',p
    assert p['report']['values']['engine_code']=='D4204T14' and not p['report']['factory_configuration_inferred']
    assert platform.get(path).json()['configuration'] is None
    r=platform.post(path+'/confirm',json={'preview_id':p['id'],'token':p['token'],'confirm':True});assert r.status_code==200,r.text
    assert platform.get(path).json()['configuration']['status']=='confirmed'
    assert platform.post(path+'/confirm',json={'preview_id':p['id'],'token':p['token'],'confirm':True}).json()['id']==r.json()['id']
    with Session(engine()) as db:assert before=={k:v for k,v in fingerprints(db).items() if k!='vehicle_configurations'}
    from sqlalchemy.exc import DBAPIError
    with Session(engine()) as db:
        with pytest.raises(DBAPIError):db.execute(text("UPDATE vehicle_configurations SET status='preview' WHERE id=:id"),{'id':r.json()['id']})
        db.rollback()
    bad=platform.post(path+'/preview',json={'facts':[dict(facts[0],kind='vin_decode') ]});assert bad.status_code==422
    conflict=platform.post(path+'/preview',json={'facts':[facts[0],dict(facts[0],value='B4204T23')]}).json()
    assert conflict['report']['conflicts']
    assert platform.post(path+'/confirm',json={'preview_id':conflict['id'],'token':conflict['token'],'confirm':True}).status_code==409

def test_configuration_isolation_and_owner_only_group_approval(platform,vehicle,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from conftest import signup
    with TestClient(app) as other:
        signup(other,'other-configuration@example.test')
        assert other.get(f"/api/v1/vehicles/{vehicle['id']}/configuration").status_code==404
        assert other.get(PREFIX+'/groups').status_code==403
        assert other.post(PREFIX+'/rules/preview',json={'type_id':'x','phrase':'specific','category':'x','subcategory':'x','evidence':'test evidence'}).status_code==403
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    assert platform.get(PREFIX+'/groups').status_code==403


def test_configuration_no_invented_options_and_stale_basis(platform,vehicle):
    from app.models import Vehicle
    path=f"/api/v1/vehicles/{vehicle['id']}/configuration"
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.engine='T5';db.commit()
    p=platform.post(path+'/preview',json={'facts':[]}).json()
    assert p['report']['values']['engine_code'] is None and p['report']['values']['options'] is None
    assert platform.post(path+'/confirm',json={'preview_id':p['id'],'token':p['token'],'confirm':True}).status_code==200
    with Session(engine()) as db:
        db.get(Vehicle,vehicle['id']).engine='D4204T14';db.commit()
    assert platform.get(path).json()['configuration']['status']=='stale'
    assert platform.post(path+'/confirm',json={'preview_id':p['id'],'token':p['token'],'confirm':True}).status_code==409


def test_group_stale_preview_rejected_and_cannot_publish_normalization(platform):
    market(platform,[row('a',part_name='Клапан контрольний Volvo XC40',category='Двигун',subcategory='Клапани',side='',position='')])
    tid=platform.post(PREFIX+'/types',json={'name':'Контрольний клапан','category':'Двигун','subcategory':'Клапани','evidence':'Inspected functional identity'}).json()['id']
    p=operation(platform,'/rules/preview',{'type_id':tid,'phrase':'клапан контрольний','category':'Двигун','subcategory':'Клапани','evidence':'Reviewed all records'})
    assert platform.post(PREFIX+'/runs',json={'mode':'publish','preview_id':p['id'],'token':p['token'],'confirm':True}).status_code==409
    market(platform,[row('b',part_name='Клапан контрольний Volvo XC40',category='Двигун',subcategory='Клапани',side='',position='')])
    r=operation(platform,'/rules/approve',{'preview_id':p['id'],'token':p['token'],'confirm':True})
    assert r['status']=='error'
    with Session(engine()) as db:assert db.scalar(select(CanonicalAlias)) is None

def test_source_price_update_keeps_identity_and_stock_unchanged(platform,vehicle,part):
    from app.models.canonical import CanonicalType,CanonicalVariant
    from app.models.catalogue import CataloguePrice
    from sqlalchemy import func
    source=row('price',part_name='Генератор Volvo XC40',category='Електрика',subcategory='Генератори',side='',position='',price_uah='100',observed_at='2026-01-01T00:00:00Z')
    market(platform,[source]);build(platform)
    with Session(engine()) as db:
        variants=set(db.scalars(select(CanonicalVariant.id)));types=set(db.scalars(select(CanonicalType.id)))
        before={k:v for k,v in fingerprints(db).items() if not k.startswith('catalogue_')}
    market(platform,[dict(source,price_uah='120',observed_at='2026-02-01T00:00:00Z')]);build(platform);build(platform)
    with Session(engine()) as db:
        assert variants==set(db.scalars(select(CanonicalVariant.id)))
        assert types==set(db.scalars(select(CanonicalType.id)))
        assert db.scalar(select(func.count()).select_from(CataloguePrice))==2
        assert before=={k:v for k,v in fingerprints(db).items() if not k.startswith('catalogue_')}

def test_installation_ordinals_and_missing_year_engine_are_not_fabricated():
    from app.services.canonical_rules import placement
    first=result('Лямбда зонд перший Volvo XC40');second=result('Лямбда зонд другий Volvo XC40')
    assert first['type_id']==second['type_id']
    assert placement(first)['id']!=placement(second)['id']
    assert not first['features'].get('engine_codes') and not first['features']['title_year_labels']


def test_existing_function_reused_and_conflicting_group_rejected(platform):
    a=platform.post(PREFIX+'/types',json={'name':'Генератор','category':'Інша категорія','subcategory':'Інша підкатегорія','evidence':'Same constructive function'}).json()['id']
    assert a==result('Генератор')['type_id']
    assert platform.post(PREFIX+'/types',json={'name':'Генератор Volvo','category':'Електрика','subcategory':'Генератори','evidence':'Invalid brand-specific function'}).status_code==422
    market(platform,[row('conflict',part_name='Генератор Volvo XC40',category='Електрика',subcategory='Генератори',side='',position='')])
    target=result('Стартер')['type_id']
    p=operation(platform,'/rules/preview',{'type_id':target,'phrase':'генератор','category':'Електрика','subcategory':'Генератори','evidence':'Deliberately conflicting proposal'})
    assert p['report']['conflict_count']==1
    done=operation(platform,'/rules/approve',{'preview_id':p['id'],'token':p['token'],'confirm':True})
    assert done['status']=='error'
