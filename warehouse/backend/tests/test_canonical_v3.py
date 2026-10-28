"""Canonical Stage 1 safety, lineage, review and read-only generator preparation."""
import json
import hashlib
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import subprocess,sys,os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,text,inspect
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Account,Part,DismantlingItem,Category,DismantlingCatalogSource,DismantlingCatalogType
from app.models.catalogue import CataloguePath,CatalogueOffer,CataloguePrice,CatalogueState
from app.models.canonical import CanonicalType,CanonicalVariant,CanonicalPlacement,CanonicalMapping,CanonicalRun,CanonicalAlias,CanonicalState
from app.services.canonical_jobs import process_one
from app.services.canonical_catalogue import analyze,base_inputs
from app.services.canonical_rules import classify,type_record,RULES
from app.services.aleto_import import BUNDLED_PACKAGE,load_package,import_package
from test_catalogue_v2 import platform,upload,plan,confirm,row

PREFIX='/api/v1/catalogue/admin/canonical'
def market(c,rows):
    j=plan(c,upload(c,rows))
    if j['report']['issues']:j=plan(c,j,{i['key']:{'action':'skip'} for i in j['report']['issues']})
    confirm(c,j)
def item(article='g1',**kw):
    return row(article,category='Електрика',subcategory='Генератори',part_name='Генератор Volvo XC40 2020 чорний',side='',position='',oem='OEM-'+article,**kw)
def build(c,publish=True):
    r=c.post(PREFIX+'/runs',json={'mode':'preview'});assert r.status_code==202,r.text
    process_one(engine());preview=c.get(PREFIX+'/runs/'+r.json()['id']).json();assert preview['status']=='done',preview
    if not publish:return preview
    r=c.post(PREFIX+'/runs',json={'mode':'publish','preview_id':preview['id'],'token':preview['token'],'confirm':True});assert r.status_code==202,r.text
    process_one(engine());done=c.get(PREFIX+'/runs/'+r.json()['id']).json();assert done['status']=='done',done
    return done

def get(c,**params):return c.get('/api/v1/catalogue/canonical/candidates',params={'manufacturer':'Volvo','model':'XC40','year':2020,**params}).json()
def fingerprints(db):
    return {t:hashlib.sha256(json.dumps(sorted(json.dumps(dict(r),sort_keys=True,default=str) for r in db.execute(text('SELECT * FROM "'+t+'"')).mappings())).encode()).hexdigest()
        for t in inspect(db.bind).get_table_names() if not t.startswith('canonical_') and t!='alembic_version'}

def test_five_generator_offers_one_function_five_oem_variants_and_base_identity(platform):
    market(platform,[item(str(i)) for i in range(5)])
    before=build(platform,False)
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(CanonicalMapping))==0
    report=build(platform)['report']
    assert report['source_offers']==5 and report['trusted_offer_fraction']==1
    types=[r for r in get(platform)['items'] if r['name']=='Генератор']
    assert len(types)==1 and types[0]['offer_count']==5 and len(types[0]['variants'])==5
    assert any(r['kind']=='base' for r in types[0]['source_refs'])
    assert types[0]['reference_prices']['UAH']['observation_count']==5
    assert types[0]['reference_prices']['UAH']['latest_observed_at']
    assert any(s['source_url'] for s in types[0]['source_refs'] if s['kind']=='v2')
    provenance=platform.get('/api/v1/catalogue/canonical/sources',params={'placement_id':types[0]['placement']['id']}).json()
    assert provenance['total']==6 and provenance['snapshot_sha']==get(platform)['snapshot_sha']
    assert all(v['attributes']['interchangeability']=='unverified' for v in types[0]['variants'])
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(CanonicalType).where(CanonicalType.name=='Генератор'))==1

def test_left_right_and_other_mount_details_not_collapsed(platform):
    market(platform,[row('left',part_name='Фара Volvo XC40 передняя левая LED',category='Електрика',subcategory='Фари',side='',position=''),
                     row('right',part_name='Фара Volvo XC40 передняя правая ксенон',category='Електрика',subcategory='Фари',side='',position='')])
    build(platform);items=[r for r in get(platform)['items'] if r['name']=='Фара']
    assert {r['placement']['side'] for r in items}=={'left','right'}
    assert len({r['canonical_type_id'] for r in items})==1 and len({r['placement']['id'] for r in items})==2
    assert sum(r['offer_count'] for r in items)==2
    assert classify({'title':'Фара передняя левая правая','category':'Електрика','key':'x','sha':'a'})['quality']=='review'

def test_same_oem_across_models_is_not_interchangeability(platform):
    market(platform,[item('one',model='XC40'),row('two',part_name='Генератор Volvo XC90',model='XC90',category='Електрика',subcategory='Генератори',side='',position='',oem='OEM-one')])
    build(platform)
    a=[r for r in get(platform)['items'] if r['name']=='Генератор'][0]['variants'][0]
    b=[r for r in get(platform,model='XC90')['items'] if r['name']=='Генератор'][0]['variants'][0]
    assert a['id']!=b['id'] and a['oem']==b['oem']
    assert a['compatibility']['status']=='possible' and b['compatibility']['status']=='possible'

@pytest.mark.parametrize('title',['ГЕНЕРАТОР VOLVO XC40 2019-2026 Б/В чорний','генератор Volvo XC40 2020 черный','Alternator Volvo XC40'])
def test_exact_ua_ru_case_cosmetic_years(title):
    a=classify({'title':title,'category':'Електрика','manufacturer':'Volvo','model':'XC40','key':'x','sha':'a'})
    b=classify({'title':'Генератор','category':'Двигун','key':'y','sha':'b'})
    assert a['quality']==b['quality']=='verified_rule' and a['type_id']==b['type_id']

@pytest.mark.parametrize('title',['Генератор імпульсів','Генератор компресора','Насос','Блок керування','OEM-12345'])
def test_no_partial_fuzzy_or_oem_only_merge(title):
    assert classify({'title':title,'category':'Електрика','oem':'OEM-12345','key':'x','sha':'a'})['quality'] in ('review','unprocessed')

def test_missing_prices_oem_and_unknown_equipment(platform):
    market(platform,[row('missing',part_name='Генератор Volvo XC40 2019-2020',oem='',price_uah='',price_usd='',category='Електрика',subcategory='Генератори',side='',position='',year_from=2019,year_to=2020)])
    build(platform);g=next(r for r in get(platform,year=2025,engine='T6')['items'] if r['name']=='Генератор')
    assert g['compatibility'] in ('possible','unknown') and g['reference_prices']['UAH']['min'] is None and g['variants'][0]['oem'] is None
    assert g['selling_price'] is None


def test_owner_context_aliases_same_name_different_functions(platform):
    market(platform,[row('engine-pump',part_name='Насос Volvo XC40',category='Двигун',subcategory='Насоси',side='',position='',oem='SAME-OEM'),
        row('brake-pump',part_name='Насос Volvo XC40',category='Гальмівна система',subcategory='Насоси',side='',position='',oem='SAME-OEM')])
    first=build(platform);assert first['report']['unprocessed_records']==2
    ids=[]
    for cat in ('Двигун','Гальмівна система'):
        r=platform.post(PREFIX+'/types',json={'name':'Насос','category':cat,'subcategory':'Насоси','evidence':'Owner functional inspection'});assert r.status_code==201,r.text
        ids.append(r.json()['id'])
        r=platform.post(PREFIX+'/aliases',json={'type_id':r.json()['id'],'phrase':'насос','category':cat,'subcategory':'Насоси','evidence':'Reviewed exact function in this category'});assert r.status_code==201,r.text
    build(platform)
    items=[r for r in get(platform)['items'] if r['name']=='Насос']
    assert len(items)==2 and len(set(ids))==2
    assert all('verified_owner' in r['quality'] for r in items)
    for entry in items:
        for v in entry['variants']:
            with Session(engine()) as db:assert db.get(CanonicalVariant,v['id']) is not None
            r=platform.post(PREFIX+'/fitments',json={'variant_id':v['id'],'manufacturer':'Volvo','model':'XC40','year_from':2020,'year_to':2020,'status':'confirmed','evidence':'Reviewed manual-alias variant identity'})
            assert r.status_code==201,r.text


def test_repeat_publication_stale_token_and_legacy_table_fingerprints(platform,vehicle,part):
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'receipt','quantity':3,'reason':'Existing stock'}).status_code==200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'sale','quantity':1,'sale_price':'77.77','sale_currency':'USD','request_key':'7a0773f6-7530-4d80-9ab5-9fe9c9a58c18'}).status_code==200
    assert platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start").status_code==200
    market(platform,[item()])
    with Session(engine()) as db:before=fingerprints(db)
    a=build(platform)
    with Session(engine()) as db:counts={t:db.scalar(select(func.count()).select_from(t)) for t in (CanonicalType,CanonicalVariant,CanonicalMapping,CanonicalPlacement)}
    b=build(platform)
    assert a['snapshot_sha']==b['snapshot_sha']
    get(platform);platform.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling/candidates")
    with Session(engine()) as db:
        assert before==fingerprints(db)
        assert counts=={t:db.scalar(select(func.count()).select_from(t)) for t in counts}
    previous=build(platform,False)
    market(platform,[item('new')])
    r=platform.post(PREFIX+'/runs',json={'mode':'publish','preview_id':previous['id'],'token':previous['token'],'confirm':True});assert r.status_code==202
    process_one(engine());assert platform.get(PREFIX+'/runs/'+r.json()['id']).json()['status']=='error'


def test_platform_allowlist_and_workspace_read_isolation(platform,vehicle,monkeypatch):
    build(platform)
    with TestClient(app) as other:
        from conftest import signup
        signup(other,'canonical-other@example.test')
        assert other.get('/api/v1/catalogue/canonical/candidates',params={'manufacturer':'Volvo','model':'XC40'}).status_code==200
        assert other.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling/candidates").status_code==404
        for path,payload in [('/runs',{'mode':'preview'}),('/types',{'name':'Насос','category':'Двигун','subcategory':'Насоси','evidence':'test evidence'}),('/aliases',{'phrase':'x','category':'x','subcategory':'x','type_id':'spoof','evidence':'test evidence'}),('/fitments',{'variant_id':'spoof','manufacturer':'Volvo','model':'XC40','status':'confirmed','evidence':'test evidence'})]:
            assert other.post(PREFIX+path,json=payload).status_code==403
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    assert platform.post(PREFIX+'/runs',json={'mode':'preview'}).status_code==403
    assert platform.get(PREFIX+'/review').status_code==403


def test_fitment_requires_explicit_coverage_and_keeps_history(platform):
    market(platform,[item()]);build(platform)
    v=next(r for r in get(platform)['items'] if r['name']=='Генератор')['variants'][0]
    assert v['compatibility']['status']=='possible'
    data={'variant_id':v['id'],'manufacturer':'Volvo','model':'XC40','year_from':2019,'year_to':2021,'engine':'T5','status':'confirmed','evidence':'Verified technical document TEST-ONLY'}
    r=platform.post(PREFIX+'/fitments',json=data);assert r.status_code==201,r.text
    g=next(r for r in get(platform,engine='T5')['items'] if r['name']=='Генератор');assert g['variants'][0]['compatibility']['status']=='confirmed'
    g=next(r for r in get(platform,engine='T6')['items'] if r['name']=='Генератор');assert g['compatibility']!='confirmed'
    g=next(r for r in get(platform,year=2018,engine='T5')['items'] if r['name']=='Генератор');assert g['compatibility']!='incompatible'
    data.update(year_from=2018,year_to=2018,status='incompatible',evidence='Explicit negative fitment TEST-ONLY')
    assert platform.post(PREFIX+'/fitments',json=data).status_code==201
    assert next(r for r in get(platform,year=2018,engine='T5')['items'] if r['name']=='Генератор')['compatibility']=='incompatible'


def test_populated_migration_is_additive(platform,vehicle,part):
    market(platform,[item()])
    with Session(engine()) as db:before=fingerprints(db)
    try:
        subprocess.run([sys.executable,'-m','alembic','downgrade','41f9a2c87d10'],check=True,capture_output=True)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)
        subprocess.run([sys.executable,'-m','alembic','check'],check=True,capture_output=True)
        with Session(engine()) as db:
            assert fingerprints(db)==before
            assert db.scalar(select(func.count()).select_from(CanonicalMapping))==0
    finally:subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)


def test_base_audit_exactly_covers_unchanged_legacy_positions():
    rows=base_inputs();assert len(rows)==33
    assert len({classify(r)['type_id'] for r in rows})==22
    assert all(classify(r)['quality']=='verified_rule' for r in rows)


def test_v1_local_and_global_bridge_is_read_only_and_tenant_local(platform,vehicle):
    from app.models import Vehicle,now
    from app.models.aleto import AletoModel,AletoOffer,AletoApplication,AletoTaxonomy,AletoPrice
    from decimal import Decimal
    build(platform)
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.manufacturer='Volvo';v.model='XC40';v.year=2020;aid=v.account_id
        root=Category(account_id=aid,name='Електрика',kind='category',source='test-v1',external_key='root');db.add(root);db.flush()
        sub=Category(account_id=aid,name='Генератори',kind='subcategory',source='test-v1',external_key='sub',parent_id=root.id);db.add(sub)
        model=AletoModel(account_id=aid,manufacturer='Volvo',model='XC40');offer=AletoOffer(account_id=aid,source_article='v1-private',title='Генератор Volvo XC40',oem='PRIVATE-OEM',condition='test',source_url='https://aleto.ua/ua/detail/test/',observed_at=now());db.add_all([model,offer]);db.flush()
        db.add(AletoApplication(account_id=aid,offer_id=offer.id,model_id=model.id));db.flush()
        db.add(AletoTaxonomy(account_id=aid,offer_id=offer.id,model_id=model.id,category_id=root.id,subcategory_id=sub.id,raw_category='Электрика',raw_subcategory='Генератор',normalization_status='verified'))
        db.add(AletoPrice(account_id=aid,offer_id=offer.id,observed_at=offer.observed_at,price_uah=Decimal('987.65'),source_url=offer.source_url))
        src=DismantlingCatalogSource(account_id=aid,source='private-local',provenance='Synthetic own vocabulary',license_reference='test');db.add(src);db.flush()
        db.add(DismantlingCatalogType(account_id=aid,source_id=src.id,catalog_key='my-generator',category_key='p',category_name='Силовий агрегат',subcategory_key='e',subcategory_name='Двигун та навісне',name='Генератор',position=''))
        db.commit();before=fingerprints(db)
    response=platform.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling/candidates");assert response.status_code==200,response.text
    g=next(r for r in response.json()['items'] if r['name']=='Генератор')
    assert g['offer_count']==1 and {s['kind'] for s in g['source_refs']}=={'base','local','v1'}
    assert g['reference_prices']['UAH']['min']=='987.65'
    # Shared model query cannot reveal the workspace-local offer/OEM/price.
    shared=next(r for r in get(platform)['items'] if r['name']=='Генератор')
    assert shared['offer_count']==0 and shared['variants']==[]
    with Session(engine()) as db:assert fingerprints(db)==before


def test_alias_correction_history_and_withdrawal_are_explicit(platform):
    market(platform,[row('ambiguous',part_name='Насос Volvo XC40',category='Двигун',subcategory='Насоси',side='',position='')]);first=build(platform)
    issue=first['report']['issues'][0]
    tid=platform.post(PREFIX+'/types',json={'name':'Насос','category':'Двигун','subcategory':'Насоси','evidence':'Reviewed pump function'}).json()['id']
    data={'type_id':tid,'source_key':issue['source_key'],'source_sha':issue['source_sha'],'evidence':'Explicit reviewed source function'}
    r=platform.post(PREFIX+'/aliases',json=data);assert r.status_code==201
    build(platform);assert any(r['name']=='Насос' for r in get(platform)['items'])
    data.update(type_id=None,enabled=False,expected_revision=1,evidence='Approval withdrawn pending structural inspection')
    assert platform.post(PREFIX+'/aliases',json=data).status_code==201
    # Until publication the old verified snapshot stays readable.
    assert any(r['name']=='Насос' for r in get(platform)['items'])
    build(platform);assert not any(r['name']=='Насос' for r in get(platform)['items'])
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(CanonicalAlias))==2
        assert db.scalar(select(func.count()).select_from(CanonicalMapping).where(CanonicalMapping.source_key==issue['source_key']))>=3
        from sqlalchemy.exc import DBAPIError
        with pytest.raises(DBAPIError):db.execute(text('UPDATE canonical_aliases SET evidence=\'rewrite\''))
        db.rollback()


def test_durable_normalization_crash_and_explicit_retry(platform):
    market(platform,[item()]);preview=build(platform,False)
    r=platform.post(PREFIX+'/runs',json={'mode':'publish','preview_id':preview['id'],'token':preview['token'],'confirm':True});assert r.status_code==202
    script="""import os
from app.db import engine
import app.services.canonical_jobs as worker
original=worker.build
def crash(*a,**kw):
 result=original(*a,**kw)
 os._exit(66)
worker.build=crash
worker.process_one(engine())
"""
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,env=dict(os.environ),timeout=30)
    assert result.returncode==66,result.stderr.decode()
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(CanonicalMapping))==0 and db.get(CanonicalState,1).snapshot_sha is None
    process_one(engine());assert platform.get(PREFIX+'/runs/'+r.json()['id']).json()['status']=='error'
    assert build(platform)['report']['committed'] is True


def test_concurrent_worker_coordination_and_ordinary_reads(platform,monkeypatch):
    from threading import Event
    import app.services.canonical_jobs as worker
    entered,release=Event(),Event();original=worker.build
    def slow(*a,**kw):entered.set();assert release.wait(10);return original(*a,**kw)
    monkeypatch.setattr(worker,'build',slow)
    r=platform.post(PREFIX+'/runs',json={'mode':'preview'});assert r.status_code==202
    assert platform.post(PREFIX+'/runs',json={'mode':'preview'}).json()['id']==r.json()['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(process_one,engine())
        try:
            assert entered.wait(5)
            assert not process_one(engine())
            assert platform.get('/health').status_code==200
            assert platform.post(PREFIX+'/types',json={'name':'Насос','category':'Двигун','subcategory':'Насоси','evidence':'Concurrent mutation test'}).status_code==409
            assert platform.get('/api/v1/catalogue/canonical/candidates',params={'manufacturer':'Volvo','model':'XC40'}).json()['published'] is False
        finally:release.set()
        assert future.result(timeout=10)


def test_startup_never_builds_or_publishes_and_csrf_is_required(platform):
    assert not process_one(engine())
    assert get(platform)['published'] is False
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(CanonicalType))==0
    csrf=platform.headers.pop('X-CSRF-Token')
    try:assert platform.post(PREFIX+'/runs',json={'mode':'preview'}).status_code==403
    finally:platform.headers['X-CSRF-Token']=csrf


def test_full_real_A_normalization_report_preserves_source_tables(platform,tmp_path):
    j=plan(platform,upload(platform,raw=BUNDLED_PACKAGE.read_bytes(),filename=BUNDLED_PACKAGE.name))
    if j['report']['issues']:j=plan(platform,j,{i['key']:{'action':'skip'} for i in j['report']['issues']})
    confirm(platform,j)
    with Session(engine()) as db:before=fingerprints(db)
    report=build(platform)['report']
    assert report['source_offers']==7246
    assert report['confirmed_mappings']+report['ambiguous_mappings']+report['unprocessed_records']==14400+33
    assert report['mapped_offers']<=7246 and 0<=report['trusted_offer_fraction']<=1
    for model in ('XC40','XC60','XC90'):
        result=get(platform,model=model);assert result['published'] and result['total']>=33
    with Session(engine()) as db:assert before==fingerprints(db)
    # Local-only evidence artifact, not a staging result or the unavailable B ZIP.
    from pathlib import Path
    destination=Path(os.environ.get('WAREHOUSE_CANONICAL_TEST_REPORT',str(tmp_path/'canonical-real-A-report.json')))
    destination.write_text(json.dumps({'dataset':'bundled real Volvo A','real_staging_B_tested':False,'report':report},ensure_ascii=False,indent=2)+'\n')


def test_real_export_modifiers_are_retained_and_never_become_fitment_claims():
    a=classify({'title':'Генератор Volvo XC90 16-22 T5 180A чорний','category':'Електрика','manufacturer':'Volvo','model':'XC90','key':'x','sha':'a'})
    b=classify({'title':'Кронштейн генератора Volvo XC90 16-22 T5','category':'Електрика','manufacturer':'Volvo','model':'XC90','key':'y','sha':'b'})
    assert a['quality']==b['quality']=='verified_rule' and a['type_id']!=b['type_id']
    assert a['features']['engine_labels']==['t5'] and a['features']['title_year_labels']==['16-22']
    assert a['features']['ratings']==['180a']
    assert classify({'title':'Генератор 12-24','category':'Електрика','key':'z','sha':'c'})['quality']=='unprocessed'


def test_conflicting_verified_context_aliases_are_queued_not_guessed(platform):
    market(platform,[row('ambiguous',part_name='Насос Volvo XC40',category='Двигун',subcategory='Насоси',side='',position='')]);build(platform)
    for name,brand in [('Насос оливи',''),('Насос охолодження','Volvo')]:
        tid=platform.post(PREFIX+'/types',json={'name':name,'category':'Двигун','subcategory':'Насоси','evidence':'Test functional definition'}).json()['id']
        r=platform.post(PREFIX+'/aliases',json={'type_id':tid,'phrase':'насос','category':'Двигун','subcategory':'Насоси','manufacturer':brand,'evidence':'Test exact scoped alias'});assert r.status_code==201,r.text
    report=build(platform)['report'];assert report['ambiguous_mappings']==1
    assert platform.get(PREFIX+'/aliases').json()['total']==2
    assert not any(r['name'].startswith('Насос') for r in get(platform)['items'])


def test_mount_axes_are_distinct_even_with_same_oem(platform):
    market(platform,[row('upper',part_name='Фара передня ліва верхня Volvo',category='Електрика',subcategory='Фари',side='',position='',oem='OEMcase'),
                     row('lower',part_name='Фара передня ліва нижня Volvo',category='Електрика',subcategory='Фари',side='',position='',oem='OEMcase')])
    build(platform)
    actual=[r for r in get(platform)['items'] if r['name']=='Фара' and r['offer_count']]
    assert len(actual)==2 and {tuple(r['placement']['details']['mount']) for r in actual}=={('upper',),('lower',)}
    assert len({r['variants'][0]['id'] for r in actual})==2
