"""Focused release audit: authorization, real A format parity and regression fixes."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models.catalogue import CatalogueJob as Job,CatalogueEntity as Entity
from app.services.catalogue_convert import convert
from app.services.catalogue_format import parse_upload
from app.services.aleto_import import BUNDLED_PACKAGE
from test_catalogue_v2 import row,csv_bytes,upload,plan,confirm,counts


@pytest.fixture
def owner(logged,monkeypatch):
    actor=logged.get('/api/v1/auth/me').json()['id']
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',actor)
    return logged


@pytest.mark.parametrize('verified_name',['Новий вузол','НОВИЙ ВУЗОЛ'])
def test_confirm_same_normalized_name_does_not_recurse(owner,verified_name):
    record={'article':'new-normalization','model':'Volvo XC40','category':'Кузов','subcategory':'Новий вузол'}
    j=plan(owner,upload(owner,[row('new-normalization',subcategory='Новий вузол',source_record=json.dumps(record,ensure_ascii=False))]))
    assert j['status']=='review'
    issue=j['report']['issues'][0]
    j=plan(owner,j,{issue['key']:{'action':'create_name','name':verified_name}})
    assert j['status']=='ready'
    confirm(owner,j)
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(Entity).where(Entity.kind=='subcategory'))==1
        saved=db.get(Job,j['id']).rows[0]
        assert saved['source_record']==record
    again=plan(owner,upload(owner,[row('new-normalization',subcategory='Новий вузол',source_record=json.dumps(record,ensure_ascii=False))]))
    assert again['status']=='ready'
    assert all(v['inserted']==v['updated']==0 for v in again['report']['counts'].values())


def test_all_admin_routes_closed_and_client_ids_cannot_impersonate(owner,monkeypatch,vehicle,part):
    actor=owner.get('/api/v1/auth/me').json()['id']
    j=plan(owner,upload(owner))
    urls=[('/api/v1/catalogue/admin/jobs','GET',None),
          (f"/api/v1/catalogue/admin/jobs/{j['id']}",'GET',None),
          ('/api/v1/catalogue/admin/entities?kind=manufacturer','GET',None),
          (f"/api/v1/catalogue/admin/jobs/{j['id']}/preview",'POST',{'resolutions':{}}),
          (f"/api/v1/catalogue/admin/jobs/{j['id']}/apply",'POST',{'preview_token':j['preview_token'],'confirm':True})]
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    for url,method,body in urls:
        r=owner.request(method,url,**({'json':body} if body is not None else {}))
        assert r.status_code==403,(url,r.text)
    upload(owner,expected=403)
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',actor)
    with TestClient(app) as stranger:
        r=stranger.post('/api/v1/auth/register',json={'name':'Other workspace','email':'audit-other@example.test','password':'audit-other-director-password'})
        assert r.status_code==201,r.text
        stranger.headers['X-CSRF-Token']=r.json()['csrf_token']
        stranger.headers['X-Actor-ID']=actor;stranger.headers['X-Account-ID']=actor
        # This DIRECTOR already has catalog.import, but it cannot confer global rights.
        assert 'catalog.import' in stranger.get('/api/v1/auth/me').json()['permissions']
        for url,method,body in urls:
            sep='&' if '?' in url else '?'
            spoofed=url+sep+'actor_id='+actor+'&account_id='+actor
            payload={**body,'actor_id':actor,'account_id':actor} if body else body
            r=stranger.request(method,spoofed,**({'json':payload} if payload is not None else {}))
            assert r.status_code==403,(url,r.text)
        upload(stranger,expected=403)
        assert stranger.get('/api/v1/parts/'+part['id']).status_code==404
        assert stranger.get('/api/v1/vehicles/'+vehicle['id']).status_code==404
        assert stranger.get('/api/v1/parts').json()['total']==0
        assert stranger.get('/api/v1/catalogue').status_code==200
        assert stranger.delete('/api/v1/catalogue/'+j['id']).status_code in (404,405)
    assert counts()['catalogue_offers']==0


@pytest.mark.parametrize('name',['..\\catalogue.csv','C:catalogue.csv','nested/catalogue.csv'])
def test_zip_windows_and_posix_paths_rejected(name):
    raw=csv_bytes([row()]);buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps({'schema_version':2,'file':name,'sha256':hashlib.sha256(raw).hexdigest()}))
        z.writestr(name,raw)
    with pytest.raises(ValueError,match='Unsafe ZIP entry'):parse_upload(buf.getvalue(),'unsafe.zip')


def test_raw_csv_converter_preserves_every_field_and_marks_unknown_normalization(tmp_path):
    original={'model':'Volvo XC60','article':'TEST-CONVERSION','category':'Электрика','subcategory':'Новий вузол',
              'title':'Синтетичний модуль XC60','oem':' OEM ORIGINAL ','condition':'SYNTHETIC TEST FIXTURE',
              'price_uah':'123.40','price_usd':'','url':'https://aleto.ua/ua/detail/converter-fixture/',
              'checked_at':'2026-10-27T12:30:00+03:00','collector_custom_field':' untouched metadata '}
    path=tmp_path/'parser.csv';buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(original));writer.writeheader();writer.writerow(original)
    path.write_bytes(buffer.getvalue().encode('utf-8-sig'))
    archive,report=convert(path)
    rows,kind=parse_upload(archive,'out.zip')
    assert kind=='v2-zip' and report['offers']==report['applications']==report['paths']==1
    parsed=rows[0]
    assert parsed['source_record']==original
    assert parsed['manufacturer']=='Volvo' and parsed['model']=='XC60'
    assert parsed['category']=='Електрика' and parsed['_raw_category']=='Электрика'
    assert parsed['price_usd'] is None and parsed['observed_at']=='2026-10-27T09:30:00+00:00'
    assert parsed['_review_subcategory'] is True
    assert not report['staging_operations']


def test_real_A_prepared_csv_conversion_is_equivalent_to_existing_v1_adapter(tmp_path):
    # Real A is bundled in Git. B is NOT available and is never simulated here.
    database=tmp_path/'real-A.sqlite3';database.write_bytes(gzip.decompress(BUNDLED_PACKAGE.read_bytes()))
    queries={
        'offers.csv':'SELECT article,title,oem,condition,price_uah,price_usd,url,checked_at,price_status FROM offers ORDER BY article',
        'applications.csv':'SELECT model,article FROM applications ORDER BY model,article',
        'taxonomy_paths.csv':'SELECT model,article,category AS category_uk,subcategory AS subcategory_source,raw_category AS category_source,raw_subcategory AS subcategory_raw FROM taxonomy_paths ORDER BY model,article,category,subcategory,raw_category,raw_subcategory',
    }
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
        for name,query in queries.items():
            cursor=connection.execute(query)
            with (tmp_path/name).open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.writer(f,lineterminator='\n');writer.writerow([c[0] for c in cursor.description]);writer.writerows(cursor)
    archive,report=convert(tmp_path)
    converted,_=parse_upload(archive,'A.zip')
    legacy,_=parse_upload(BUNDLED_PACKAGE.read_bytes(),BUNDLED_PACKAGE.name)
    assert (report['offers'],report['applications'],report['paths'])==(7246,10112,14400)
    def canonical(rows):
        return sorted(json.dumps({k:v for k,v in r.items() if k!='source_record'},sort_keys=True,ensure_ascii=False) for r in rows)
    assert canonical(converted)==canonical(legacy)
    assert all(r['source_record']['article']==r['source_article'] for r in converted)


def test_converter_rejects_unknown_model_or_missing_fields_instead_of_guessing(tmp_path):
    p=tmp_path/'B-not-provided.csv';p.write_text('article,title\n1,not-enough-data\n')
    with pytest.raises(ValueError,match='lacks'):convert(p)
    from app.services.catalogue_convert import split_model
    with pytest.raises(ValueError,match='manufacturer'):split_model('Land Rover Defender')
    assert split_model('Land Rover Defender','Land Rover')==('Land Rover','Defender')
