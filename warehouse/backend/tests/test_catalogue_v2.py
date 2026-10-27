"""Global catalogue, persisted owner preview/apply and unmodified tenant stock."""
import csv
import gzip
import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,text,inspect
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Account,Part,Vehicle,Operation,Category
from app.models.catalogue import CatalogueEntity as Entity,CatalogueOffer as Offer,CataloguePrice as Price,CatalogueApplication as Application,CataloguePath as CPath,CatalogueJob as Job,CatalogueAlias as Alias,CatalogueState as State
from app.models.aleto import AletoOffer
from app.services.aleto_import import BUNDLED_PACKAGE,load_package,import_package
from app.services.catalogue_format import parse_upload,MAX_UPLOAD,MAX_EXPANDED
from app.services.catalogue_import import preview,apply
from app.services.inventory import snapshot


def row(article='demo-1',**changes):
    return {'schema_version':'2','source':'aleto','source_article':article,'manufacturer':'Volvo','model':'XC40',
        'category':'Кузов','subcategory':'Бампери','part_name':'Бампер передній','side':'ліва','position':'передня',
        'oem':'TEST-OEM','condition':'synthetic test fixture','price_uah':'100.00','price_usd':'2.00',
        'source_url':'https://aleto.ua/ua/detail/test-fixture/','observed_at':'2026-10-27T12:00:00+00:00',**changes}


def csv_bytes(rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=keys);writer.writeheader();writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')


def upload(c,rows=None,raw=None,filename='test.csv',expected=201):
    r=c.post('/api/v1/catalogue/admin/jobs',content=raw if raw is not None else csv_bytes(rows or [row()]),
        headers={'Content-Type':'application/octet-stream','X-Catalogue-Filename':filename})
    assert r.status_code==expected,r.text
    return r.json()


def plan(c,job,resolutions=None,expected=200):
    r=c.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/preview",json={'resolutions':resolutions or {}})
    assert r.status_code==expected,r.text
    return r.json()


def confirm(c,job,expected=200):
    r=c.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/apply",json={'preview_token':job['preview_token'],'confirm':True})
    assert r.status_code==expected,r.text
    return r.json()


@pytest.fixture
def platform(logged,monkeypatch):
    owner=logged.get('/api/v1/auth/me').json()
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner['id'])
    return logged


def counts():
    with Session(engine()) as db:
        return {cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in (Entity,Offer,Price,Application,CPath,Alias)}


def test_closed_by_default_and_actor_role_not_workspace_or_catalog_permission(logged,monkeypatch):
    owner=logged.get('/api/v1/auth/me').json()
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',raising=False)
    assert logged.get('/api/v1/catalogue/capabilities').json()=={'platform_admin':False}
    upload(logged,expected=403)
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner['id'])
    assert logged.get('/api/v1/auth/me').json()['catalogue_platform_admin'] is True
    from app.services.auth import hasher
    for role in ('ADMIN','MANAGER'):
        with Session(engine()) as db:
            worker=Account(email=role.lower()+'@example.test',name=role,role=role,workspace_account_id=owner['id'],
                           permissions=['catalog.import','catalog.view','vehicles.view'],password_hash=hasher.hash('worker-long-password'))
            db.add(worker);db.commit();wid=worker.id
        with TestClient(app) as c:
            r=c.post('/api/v1/auth/login',json={'email':role.lower()+'@example.test','password':'worker-long-password'})
            assert r.status_code==200,r.text
            c.headers['X-CSRF-Token']=r.json()['csrf_token']
            upload(c,expected=403)
            monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner['id']+','+wid)
            upload(c,expected=403)  # Even allowlisted staff are not platform directors.
    with TestClient(app) as outsider:
        r=outsider.post('/api/v1/auth/register',json={'email':'outsider@example.test','name':'Other director','password':'other-director-password'})
        outsider.headers['X-CSRF-Token']=r.json()['csrf_token']
        upload(outsider,expected=403)
        assert outsider.get('/api/v1/catalogue/admin/jobs').status_code==403
    with TestClient(app) as anonymous:
        upload(anonymous,expected=401)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Job))==0


def test_preview_durable_apply_explicit_and_shared_reading(platform):
    job=upload(platform)
    assert job['status']=='uploaded'
    before=counts();job=plan(platform,job)
    assert job['status']=='ready' and job['report']['committed'] is False
    assert counts()==before
    loaded=platform.get(f"/api/v1/catalogue/admin/jobs/{job['id']}").json()
    assert loaded['preview_token']==job['preview_token']
    assert platform.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/apply",json={'preview_token':job['preview_token'],'confirm':False}).status_code==422
    assert platform.post(f"/api/v1/catalogue/admin/jobs/{job['id']}/apply",json={'preview_token':job['preview_token'],'confirm':'true'}).status_code==422
    assert confirm(platform,job)['status']=='applied'
    assert confirm(platform,job)['status']=='applied'  # Request replay.
    assert counts()['catalogue_offers']==1
    with TestClient(app) as another:
        r=another.post('/api/v1/auth/register',json={'email':'global-reader@example.test','name':'Reader','password':'reader-long-password'})
        another.headers['X-CSRF-Token']=r.json()['csrf_token']
        data=another.get('/api/v1/catalogue').json()
        assert data['total']==1 and data['items'][0]['price_uah']=='100.00'
        assert another.get('/api/v1/catalogue/admin/jobs/'+job['id']).status_code==403
        assert 'XC40' in next(b['models'] for b in another.get('/api/v1/vehicle-catalog').json()['brands'] if b['name']=='Volvo')
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Part))==0
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='model'))==1
        part=db.scalar(select(Entity).where(Entity.kind=='part_type'))
        assert part.name=='Бампер передній' and part.details['side']=='ліва' and part.details['oem']=='TEST-OEM'


def test_repeat_increment_price_history_and_new_brands(platform):
    confirm(platform,plan(platform,upload(platform)))
    incremental=[row(price_uah='120.00',observed_at='2026-10-28T12:00:00+00:00'),row('new-volvo',subcategory='Оптика',part_name='Фара ліва',price_uah=''),
                 row('bmw-1',manufacturer='BMW',model='X5',part_name='Бампер BMW',price_uah='55.00'),
                 row('audi-1',manufacturer='Audi',model='Q7',part_name='Бампер Audi',price_uah='60.00')]
    j=plan(platform,upload(platform,incremental))
    assert j['report']['counts']['offers']['inserted']==3 and j['report']['counts']['prices']['inserted']==4
    sample=next(p for p in j['report']['price_changes'] if p['source_article']=='demo-1')
    assert sample['previous_uah']=='100.00' and sample['price_uah']=='120.00'
    confirm(platform,j)
    after=counts();assert after['catalogue_offers']==4 and after['catalogue_prices']==5
    again=plan(platform,upload(platform,incremental))
    assert all(c['inserted']==c['updated']==0 for c in again['report']['counts'].values())
    confirm(platform,again);assert counts()==after
    data=platform.get('/api/v1/catalogue').json()
    assert next(r for r in data['items'] if r['source_article']=='demo-1')['price_uah']=='120.00'
    assert next(r for r in data['items'] if r['source_article']=='new-volvo')['price_uah'] is None
    # Same OEM never merges articles or different canonical characteristics.
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Offer))==4


def test_unknown_review_aliases_explicit_merges_and_unicode(platform):
    confirm(platform,plan(platform,upload(platform)))
    j=plan(platform,upload(platform,[row('second',manufacturer='VOLVO',model='xc40',subcategory='Комп')]))
    assert j['status']=='review' and j['report']['unresolved_total']==1
    assert confirm(platform,j,expected=409)
    issue=j['report']['issues'][0]
    target=issue['candidates'][0]['id']
    j=plan(platform,j,{issue['key']:{'action':'target','target_id':target}})
    assert j['status']=='ready';confirm(platform,j)
    assert counts()['catalogue_aliases']==1
    repeated=plan(platform,upload(platform,[row('third',manufacturer='Volvo',subcategory='Комп')]))
    assert repeated['report']['unresolved_total']==0
    confirm(platform,repeated)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='manufacturer'))==1
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='model'))==1
    # A new spelling may be explicitly merged through a preview suggestion.
    j=plan(platform,upload(platform,[row('alias-brand',manufacturer='Вольво')]))
    suggestion=next(s for s in j['report']['suggestions'] if s['kind']=='manufacturer')
    existing=suggestion['candidates'][0]['id']
    confirm(platform,plan(platform,j,{suggestion['key']:{'action':'target','target_id':existing}}))
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='manufacturer'))==1


def test_source_article_conflicts_and_immutable_observations(platform):
    confirm(platform,plan(platform,upload(platform)))
    for changes in ({'oem':'DIFFERENT'},{'price_uah':'99.00'}):
        j=plan(platform,upload(platform,[row(**changes)]))
        assert j['status']=='review' and j['report']['unresolved_total']==1
        issue=j['report']['issues'][0]
        confirm(platform,plan(platform,j,{issue['key']:{'action':'skip'}}))
    contradictory=plan(platform,upload(platform,[row('conflict'),row('conflict',oem='OTHER')]))
    assert contradictory['status']=='review'
    with Session(engine()) as db:
        assert db.scalar(select(Offer.properties))['oem']=='TEST-OEM'
        assert db.scalar(select(Price.price_uah))==100


def test_stale_preview_payload_tamper_restart_and_concurrency(platform):
    first=plan(platform,upload(platform));second=plan(platform,upload(platform,[row('second')]))
    confirm(platform,first)
    assert platform.post(f"/api/v1/catalogue/admin/jobs/{second['id']}/apply",json={'preview_token':second['preview_token'],'confirm':True}).status_code==409
    second=plan(platform,second)
    # A new process/session can apply the stored plan without browser data.
    with Session(engine()) as db:actor=db.get(Job,second['id']).actor_id
    def execute(_):
        with Session(engine()) as db:
            result=apply(db,second['id'],actor,second['preview_token']);db.commit();return result.status
    with ThreadPoolExecutor(max_workers=2) as executor:assert list(executor.map(execute,range(2)))==['applied','applied']
    assert counts()['catalogue_offers']==2
    third=plan(platform,upload(platform,[row('third')]))
    with Session(engine()) as db:
        job=db.get(Job,third['id']);changed=deepcopy(job.rows);changed[0]['oem']='tampered';job.rows=changed;db.commit()
    assert platform.post(f"/api/v1/catalogue/admin/jobs/{third['id']}/apply",json={'preview_token':third['preview_token'],'confirm':True}).status_code==409


def test_upload_zip_checks_limits_csrf_and_failed_history(platform):
    data=csv_bytes([row()]);manifest={'schema_version':2,'file':'catalogue.csv','sha256':hashlib.sha256(data).hexdigest()}
    def zipped(m=manifest,path='catalogue.csv',body=data):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',json.dumps(m));z.writestr(path,body)
        return output.getvalue()
    j=upload(platform,raw=zipped(),filename='test.zip');assert j['format']=='v2-zip'
    upload(platform,raw=zipped(path='../catalogue.csv'),expected=422)
    upload(platform,raw=zipped({**manifest,'sha256':'0'*64}),expected=422)
    upload(platform,raw=zipped(body=b'a'*2_000_000),expected=422)
    upload(platform,raw=b'bad,csv\n1,2\n',expected=422)
    upload(platform,raw=b'x'*(MAX_UPLOAD+1),expected=413)
    csrf=platform.headers.pop('X-CSRF-Token')
    try:upload(platform,expected=403)
    finally:platform.headers['X-CSRF-Token']=csrf
    history=platform.get('/api/v1/catalogue/admin/jobs').json()
    assert any(j['status']=='failed' for j in history['items'])


@pytest.mark.parametrize('changes',[{'price_uah':'NaN'},{'price_usd':'-1'},{'observed_at':'2026-10-27T12:00:00'},{'source_url':'javascript:alert(1)'},{'year_from':'2020','year_to':'2019'},{'source_url':'https://evil.example/'}])
def test_format_validation(changes):
    with pytest.raises(ValueError):parse_upload(csv_bytes([row(**changes)]),'test.csv')


def test_full_volvo_v1_then_incremental_and_repeat_preserves_legacy(platform,vehicle,part):
    # Seed old v1 independently, plus nonzero stock and personal prices/audit.
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'receipt','quantity':3,'reason':'Existing v2 regression fixture'}).status_code==200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'reserve','quantity':1,'reason':'Keep reservation'}).status_code==200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'sale','quantity':1,'sale_price':'77.77','sale_currency':'USD','request_key':str(uuid4())}).status_code==200
    buyer=platform.post('/api/v1/buyers',json={'name':'V2 fixture buyer','phone':'0501234567'}).json()
    order=platform.post('/api/v1/orders',json={'request_key':str(uuid4()),'buyer_id':buyer['id'],'lines':[{'part_id':part['id'],'quantity':1,'unit_price':'44.44','currency':'USD'}]})
    assert order.status_code==201,order.text
    legacy=load_package(BUNDLED_PACKAGE)
    with Session(engine()) as db:
        actor=db.scalar(select(Account.id).where(Account.role=='DIRECTOR'))
        # Use a small legacy v1 subset to prove the original reader is unchanged;
        # the full 7246-offer package is ingested into the global v2 catalogue below.
        offer=legacy['offers'][0];article=offer['article']
        subset={**legacy,'offers':[offer],'applications':[(m,a) for m,a in legacy['applications'] if a==article],
                'paths':[p for p in legacy['paths'] if p['article']==article]}
        import_package(db,actor,subset);db.commit()
        protected=original_fingerprints(db)
    a=upload(platform,raw=BUNDLED_PACKAGE.read_bytes(),filename='aleto-v1.sqlite3.gz')
    a=plan(platform,a)
    assert a['report']['counts']['offers']['inserted']==7246
    resolutions={i['key']:{'action':'skip'} for i in a['report']['issues']}
    if resolutions:a=plan(platform,a,resolutions)
    assert a['status']=='ready',a['report']['issues']
    confirm(platform,a)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Offer))==7246
        assert db.scalar(select(func.count()).select_from(Application))==10112
        assert db.scalar(select(func.count()).select_from(CPath))==14400
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='part_type'))>101
    # Reuse exact, real source metadata; ONLY changed values below are synthetic.
    initial=legacy['offers'][0]
    model=next(m for m,a in legacy['applications'] if a==initial['article']).split(' ',1)[1]
    common=dict(part_name=initial['title'],oem=initial['oem'] or '',condition=initial['condition'],source_url=initial['url'],
                model=model,observed_at=initial['observed_at'].isoformat(),price_uah=str(initial['price_uah']) if initial['price_uah'] else '',
                price_usd=str(initial['price_usd']) if initial['price_usd'] else '')
    unchanged=row(initial['article'],side='',position='',**common)
    changed={**unchanged,'price_uah':'12345.67','observed_at':'2026-10-29T12:00:00+00:00'}
    incremental=[unchanged,changed,row('SYNTHETIC-NEW',subcategory='Тестова нова підкатегорія',part_name='Синтетична деталь',price_uah=''),
                 row('SYNTHETIC-PENDING',subcategory='Комп',part_name='Синтетична неоднозначна деталь')]
    b=plan(platform,upload(platform,incremental))
    decision={i['key']:{'action':'skip'} for i in b['report']['issues']}
    if decision:b=plan(platform,b,decision)
    confirm(platform,b)
    before=counts()
    assert before['catalogue_offers']==7248 and before['catalogue_prices']==7249
    c=plan(platform,upload(platform,incremental))
    if c['report']['issues']:c=plan(platform,c,{i['key']:{'action':'skip'} for i in c['report']['issues']})
    assert all(v['inserted']==v['updated']==0 for v in c['report']['counts'].values())
    confirm(platform,c);assert counts()==before
    with Session(engine()) as db:
        assert original_fingerprints(db)==protected



def original_fingerprints(db):
    result={}
    for table in inspect(db.bind).get_table_names():
        if table.startswith('catalogue_'):continue
        rows=sorted(json.dumps(dict(r),sort_keys=True,default=str,ensure_ascii=False) for r in db.execute(text('SELECT * FROM "'+table+'"')).mappings())
        result[table]=hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return result


def test_owner_revocation_and_alias_target_validation(platform,monkeypatch):
    initial=plan(platform,upload(platform))
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    confirm(platform,initial,expected=403)
    assert counts()['catalogue_offers']==0
    with Session(engine()) as db:
        actor=db.scalar(select(Account).where(Account.role=='DIRECTOR'))
        aid=actor.id;actor.is_active=False;db.commit()
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',aid)
    assert platform.get('/api/v1/catalogue/capabilities').status_code==401


def test_mapping_change_invalidates_token_and_invalid_alias_parent_is_rejected(platform):
    confirm(platform,plan(platform,upload(platform)))
    j=plan(platform,upload(platform,[row('pending',subcategory='Комп')]))
    issue=j['report']['issues'][0]
    with Session(engine()) as db:
        manufacturer=db.scalar(select(Entity.id).where(Entity.kind=='manufacturer'))
    plan(platform,j,{issue['key']:{'action':'target','target_id':manufacturer}},expected=422)
    old=j['preview_token']
    j=plan(platform,j,{issue['key']:{'action':'create_name','name':'Перевірена підкатегорія'}})
    assert j['status']=='ready' and j['preview_token']!=old
    assert platform.post(f"/api/v1/catalogue/admin/jobs/{j['id']}/apply",json={'preview_token':old,'confirm':True}).status_code==409
    confirm(platform,j)


def test_database_constraints_and_price_history_immutable(platform):
    from sqlalchemy.exc import DBAPIError,IntegrityError
    confirm(platform,plan(platform,upload(platform)))
    for action in ('UPDATE catalogue_prices SET price_uah=0','DELETE FROM catalogue_prices'):
        with pytest.raises(DBAPIError):
            with engine().begin() as c:c.execute(text(action))
    with pytest.raises(IntegrityError):
        with engine().begin() as c:
            c.execute(text("INSERT INTO catalogue_entities(id,kind,parent_id,parent_kind,name,normalized_name,identity_key,details) VALUES ('bad','model',NULL,NULL,'bad','bad','bad','{}')"))


def test_concurrent_distinct_jobs_require_repreview_after_catalogue_change(platform):
    jobs=[plan(platform,upload(platform,[row(str(i))])) for i in range(2)]
    with Session(engine()) as db:actor=db.get(Job,jobs[0]['id']).actor_id
    def execute(j):
        with Session(engine()) as db:
            try:
                apply(db,j['id'],actor,j['preview_token']);db.commit();return 200
            except Exception as e:
                db.rollback()
                if getattr(e,'status_code',None)==409:return 409
                raise
    with ThreadPoolExecutor(max_workers=2) as executor:assert sorted(executor.map(execute,jobs))==[200,409]
    assert counts()['catalogue_offers']==1


def test_additive_migration_roundtrip_keeps_v1_and_business_data(platform,vehicle,part):
    import subprocess,sys
    with Session(engine()) as db:before=original_fingerprints(db)
    try:
        subprocess.run([sys.executable,'-m','alembic','downgrade','b8716962f6b8'],check=True,capture_output=True)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)
        subprocess.run([sys.executable,'-m','alembic','check'],check=True,capture_output=True)
        with Session(engine()) as db:
            after=original_fingerprints(db)
            assert before==after
    finally:
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True,capture_output=True)


def test_v2_alias_unicode_and_known_part_traits_are_not_lost(platform):
    confirm(platform,plan(platform,upload(platform,[
        row('unicode-1',manufacturer='Volvo\u0301',side='ліва'),
        row('unicode-2',manufacturer='VOLVÓ',side='права')])) )
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='manufacturer'))==1
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='model'))==1
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='part_type'))==2
        assert db.scalar(select(func.count()).select_from(Offer))==2


def test_metadata_update_requires_manual_confirmation_and_preserves_price_history(platform):
    confirm(platform,plan(platform,upload(platform)))
    changed=row(condition='synthetic updated condition',observed_at='2026-10-28T12:00:00+00:00',price_uah='200.00')
    j=plan(platform,upload(platform,[changed]))
    assert j['status']=='review'
    issue=j['report']['issues'][0]
    j=plan(platform,j,{issue['key']:{'action':'accept_incoming'}})
    confirm(platform,j)
    with Session(engine()) as db:
        assert db.scalar(select(Offer.properties))['condition']=='synthetic updated condition'
        assert db.scalar(select(func.count()).select_from(Price))==2


def test_process_crash_before_commit_leaves_ready_job_and_no_partial_catalogue(platform):
    import subprocess,sys
    j=plan(platform,upload(platform))
    with Session(engine()) as db:actor=db.get(Job,j['id']).actor_id
    script='''
import os,sys
from sqlalchemy.orm import Session
from app.db import engine
from app.services.catalogue_import import apply
with Session(engine()) as db:
    apply(db,sys.argv[1],sys.argv[2],sys.argv[3])
    db.flush()
    os._exit(9)
'''
    result=subprocess.run([sys.executable,'-c',script,j['id'],actor,j['preview_token']],capture_output=True)
    assert result.returncode==9
    assert counts()['catalogue_offers']==0
    with Session(engine()) as db:assert db.get(Job,j['id']).status=='ready'
    assert confirm(platform,j)['status']=='applied'


def test_archive_duplicate_symlink_and_gzip_bomb_are_rejected(tmp_path):
    import stat
    data=csv_bytes([row()]);manifest={'schema_version':2,'file':'catalogue.csv','sha256':hashlib.sha256(data).hexdigest()}
    for mode in ('duplicate','symlink'):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json',json.dumps(manifest))
            if mode=='duplicate':
                z.writestr('catalogue.csv',data)
                with pytest.warns(UserWarning,match='Duplicate'):z.writestr('catalogue.csv',data)
            else:
                entry=zipfile.ZipInfo('catalogue.csv');entry.create_system=3;entry.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(entry,b'/etc/passwd')
        with pytest.raises(ValueError):parse_upload(output.getvalue(),'unsafe.zip')
    with pytest.raises(ValueError,match='ratio'):parse_upload(gzip.compress(b'x'*2_000_000),'bomb.gz')
    import sqlite3
    path=tmp_path/'malicious.sqlite3'
    with sqlite3.connect(path) as c:c.execute('CREATE VIEW offers AS SELECT 1')
    with pytest.raises(ValueError,match='views/triggers'):parse_upload(path.read_bytes(),'malicious.sqlite3')



def test_explicit_skip_never_erases_existing_verified_path(platform):
    confirm(platform,plan(platform,upload(platform)))
    with Session(engine()) as db:
        old=db.scalar(select(CPath)).part_type_id
        key=db.scalar(select(Entity.identity_key).where(Entity.kind=='subcategory'))
    j=plan(platform,upload(platform),{key:{'action':'skip'}})
    assert j['report']['counts']['paths']['updated']==0
    confirm(platform,j)
    with Session(engine()) as db:assert db.scalar(select(CPath)).part_type_id==old



def test_skip_unknown_manufacturer_preserves_readable_source_offer_without_inventing_model(platform):
    j=plan(platform,upload(platform,[row('unknown-brand',manufacturer='Unknown')]))
    issue=j['report']['issues'][0]
    assert issue['kind']=='manufacturer'
    confirm(platform,plan(platform,j,{issue['key']:{'action':'skip'}}))
    assert platform.get('/api/v1/catalogue').json()['total']==1
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Application))==0
        assert db.scalar(select(func.count()).select_from(Price))==1



def test_json_control_body_bound_before_parse_and_wrong_mime_cannot_bypass(platform):
    from app.api.catalogue_limits import MAX_CONTROL_BODY
    for content_type in ('application/json','application/octet-stream',''):
        r=platform.post('/api/v1/catalogue/admin/jobs/not-a-job/preview',content=(b' '*MAX_CONTROL_BODY)+b'X',headers={'Content-Type':content_type})
        assert r.status_code==413
    r=platform.post('/api/v1/catalogue/admin/jobs/not-a-job/preview',content=b'{broken',headers={'Content-Type':'application/json'})
    assert r.status_code==422
    # Automatic file detection is independent of MIME; auth remains mandatory.
    r=platform.post('/api/v1/catalogue/admin/jobs',content=csv_bytes([row()]),headers={'Content-Type':'application/json','X-Catalogue-Filename':'mime.csv'})
    assert r.status_code==201,r.text
    assert plan(platform,r.json())['status']=='ready'
