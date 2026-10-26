"""Persistent plan, confirmed receipts and scalable account-local catalogue."""
from concurrent.futures import ThreadPoolExecutor
from subprocess import run
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import DismantlingItem,VehicleChecklistItem
from conftest import signup


@pytest.fixture
def donor(logged):
    row=logged.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2010}).json()
    assert logged.post(base(row)+'/start').status_code==200
    return row


def base(donor):return '/api/v1/vehicles/'+donor['id']+'/dismantling'

def view(client,donor,query=''):return client.get(base(donor)+'/workspace'+query).json()

def post(client,donor,path,body):
    if path=='/batch' and 'selection_token' not in body:
        from urllib.parse import urlencode
        scope={k:body[k] for k in ['source','category_key','subcategory_key','q'] if k in body}
        response=view(client,donor,'?'+urlencode(scope))
        body={**body,'selection_token':response['scope_tokens']['receipt' if body['action']=='receipt' else 'mark']}
    return client.post(base(donor)+path,json=body)

def catalog(count=1):
    return {'source':'own.catalog','provenance':'Independent offline test vocabulary, not real inventory',
        'license_reference':'Own test data, permitted storage','rights_confirmed':True,
        'types':[{'catalog_key':f'test-{i}','category_key':'test','category_name':'Test category',
            'subcategory_key':'test-sub','subcategory_name':'Test subcategory','name':f'Test type {i}','position':''} for i in range(count)]}


def test_plan_defaults_persists_and_never_changes_status_stock_or_catalog(logged,donor):
    data=view(logged,donor)
    assert data['counts']=={'total':33,'included':33,'excluded':0,'dismantled':0,'received':0}
    row=data['items'][0]
    for included in [False,True,False]:
        assert post(logged,donor,'/plan',{'ids':[row['id']],'included':included}).status_code==200
        stored=next(r for r in view(logged,donor)['items'] if r['id']==row['id'])
        assert stored['included'] is included and stored['status']=='unchecked' and stored['part_id'] is None
    assert logged.post(base(donor)+'/start').json()['created']==0
    assert view(logged,donor)['counts']['excluded']==1
    assert logged.get('/api/v1/parts').json()['total']==0
    assert len(__import__('app.services.dismantling',fromlist=['CATALOG']).CATALOG['categories'])==6


def test_receipt_requires_included_and_explicit_dismantled_status(logged,donor):
    row=view(logged,donor)['items'][0];ids=[row['id']]
    assert post(logged,donor,'/actions',{'ids':ids,'action':'receipt'}).status_code==409
    post(logged,donor,'/actions',{'ids':ids,'action':'damaged'})
    assert post(logged,donor,'/actions',{'ids':ids,'action':'receipt'}).status_code==409
    post(logged,donor,'/actions',{'ids':ids,'action':'dismantled'})
    post(logged,donor,'/plan',{'ids':ids,'included':False})
    assert post(logged,donor,'/actions',{'ids':ids,'action':'receipt'}).status_code==409
    post(logged,donor,'/plan',{'ids':ids,'included':True})
    assert post(logged,donor,'/actions',{'ids':ids,'action':'receipt'}).json()['updated']==1
    before=logged.get('/api/v1/parts').json()['items'][0]
    assert before['quantity']==1 and before['condition']=='damaged'
    post(logged,donor,'/plan',{'ids':ids,'included':False})
    post(logged,donor,'/plan',{'ids':ids,'included':True})
    assert logged.get('/api/v1/parts').json()['items'][0]==before
    assert post(logged,donor,'/actions',{'ids':ids,'action':'receipt'}).json()['updated']==0


def test_category_subcategory_scope_and_bulk_confirmation(logged,donor):
    data=view(logged,donor);group=data['hierarchy'][0]
    scope={k:group[k] for k in ('source','category_key')}
    assert post(logged,donor,'/plan',{**scope,'included':False}).status_code==200
    excluded=view(logged,donor)['counts']['excluded'];assert excluded>1
    sub={**scope,'subcategory_key':group['subcategory_key']}
    post(logged,donor,'/plan',{**sub,'included':True})
    assert view(logged,donor)['counts']['included']==33-excluded+group['total']
    post(logged,donor,'/plan',{**scope,'included':True})
    assert view(logged,donor)['counts']['included']==33
    query='?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode(scope)
    expected=view(logged,donor,query)['scope_counts']['mark']
    assert post(logged,donor,'/batch',{**scope,'action':'dismantled','expected_count':expected+1}).status_code==409
    assert post(logged,donor,'/batch',{**scope,'action':'dismantled','expected_count':expected}).json()['updated']==expected
    assert logged.get('/api/v1/parts').json()['total']==0
    receipt={**scope,'action':'receipt','expected_count':expected,'quantity':1}
    assert post(logged,donor,'/batch',receipt).json()['updated']==expected
    assert post(logged,donor,'/batch',receipt).json()['updated']==0
    assert logged.get('/api/v1/parts').json()['total']==expected


def test_import_rights_validation_dry_run_and_account_isolation(logged,donor):
    path='/api/v1/dismantling/catalog/import';data=catalog(2)
    assert logged.post(path,json={**data,'rights_confirmed':False}).status_code==422
    assert logged.post(path,json={**data,'source':'carpot.base.v1'}).status_code==422
    assert logged.post(path,json={**data,'types':[data['types'][0],data['types'][0]]}).status_code==422
    assert logged.post(path+'?dry_run=true',json=data).json()['created']==2
    assert logged.post(base(donor)+'/start').json()['created']==0
    assert logged.post(path,json=data).json()['created']==2
    assert view(logged,donor)['counts']['total']==33 # import itself never touches donor
    assert logged.post(base(donor)+'/start').json()['created']==2
    assert view(logged,donor)['counts']['included']==35
    with TestClient(app) as other:
        assert other.post(path,json=data).status_code==401
        signup(other,'catalog-other@example.test')
        vehicle=other.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2010}).json()
        assert other.post(base(vehicle)+'/start').json()['created']==33
        assert other.get(base(donor)+'/workspace').status_code==404
        assert post(other,donor,'/plan',{'ids':[view(logged,donor)['items'][0]['id']],'included':False}).status_code==404
    logged.headers.pop('X-CSRF-Token')
    assert logged.post(path,json=data).status_code==403
    assert post(logged,donor,'/plan',{'included':False,'ids':[view(logged,donor)['items'][0]['id']]}).status_code==403


def test_large_catalog_is_paged_and_scopes_apply_beyond_page(logged,donor):
    payload=catalog(1205)
    assert logged.post('/api/v1/dismantling/catalog/import',json=payload).status_code==200
    assert logged.post(base(donor)+'/start').json()['created']==1205
    data=view(logged,donor,'?q=Test%20type&limit=100')
    assert data['total']==1205 and len(data['items'])==100
    group=next(g for g in data['hierarchy'] if g['category_key']=='test')
    scope={k:group[k] for k in ('source','category_key')}
    assert post(logged,donor,'/plan',{**scope,'included':False}).json()['updated']==1205
    assert view(logged,donor)['counts']['excluded']==1205
    post(logged,donor,'/plan',{**scope,'included':True})
    assert post(logged,donor,'/batch',{**scope,'action':'dismantled','expected_count':1000}).status_code==422
    page=view(logged,donor,'?q=Test%20type&offset=100&limit=100')
    assert not set(r['id'] for r in page['items'])&set(r['id'] for r in data['items'])


def test_reimport_preserves_vehicle_choices_and_history(logged,donor):
    path='/api/v1/dismantling/catalog/import';payload=catalog()
    logged.post(path,json=payload);logged.post(base(donor)+'/start')
    row=next(r for r in view(logged,donor)['items'] if r['catalog_key']=='test-0')
    post(logged,donor,'/plan',{'ids':[row['id']],'included':False})
    payload['types'][0]['name']='Updated catalogue name'
    assert logged.post(path,json=payload).json()['updated']==1
    logged.post(base(donor)+'/start')
    after=next(r for r in view(logged,donor)['items'] if r['id']==row['id'])
    assert after['included'] is False and after['name']==row['name']
    assert logged.get('/api/v1/parts').json()['total']==0


def test_v2_readiness_and_migration_keep_existing_receipts_planparts_and_sales(logged,donor):
    row=view(logged,donor)['items'][0]
    post(logged,donor,'/actions',{'ids':[row['id']],'action':'dismantled'})
    post(logged,donor,'/actions',{'ids':[row['id']],'action':'receipt','quantity':2})
    part=logged.get('/api/v1/parts').json()['items'][0]
    logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'sale','quantity':1,'reason':'Real explicit local test sale'})
    with Session(engine()) as db:
        p=VehicleChecklistItem(account_id=donor['account_id'],vehicle_id=donor['id'],ktype=9743,pt_id=1,name_en='Mirror',name_uk='Дзеркало',article_count=10,status='present');db.add(p);db.commit();provider_id=p.id
    before=logged.get('/api/v1/parts/'+part['id']).json()
    run([sys.executable,'-m','alembic','downgrade','d53c9a27f608'],check=True)
    try:
        assert logged.get('/api/v1/dismantling/workspace-readiness').status_code==503
        run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        result=logged.get('/api/v1/dismantling/workspace-readiness').json()
        assert result['contract_version']==2 and result['database_revisions']==['b94f62d18e07']
        assert logged.get('/api/v1/dismantling/readiness').json()['contract_version']==1
        restored=next(r for r in view(logged,donor)['items'] if r['id']==row['id'])
        assert restored['included'] and restored['received_at'] and restored['quantity']==2
        assert logged.get('/api/v1/parts/'+part['id']).json()==before
        assert logged.get(base(donor)).json()['sold_units']==1
        with Session(engine()) as db:assert db.get(VehicleChecklistItem,provider_id).name_uk=='Дзеркало'
        run([sys.executable,'-m','alembic','check'],check=True)
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True)


def test_concurrent_exclusion_and_receipt_are_serialized(logged,donor):
    from fastapi import HTTPException
    from app.api.dismantling import DismantlingAction,PlanUpdate
    from app.services import dismantling
    row=view(logged,donor)['items'][0]
    post(logged,donor,'/actions',{'ids':[row['id']],'action':'dismantled'})
    def run_action(kind):
        with Session(engine()) as db:
            try:
                if kind=='exclude':result=dismantling.change_plan(db,donor['id'],donor['account_id'],PlanUpdate(ids=[row['id']],included=False))
                else:result=dismantling.actions(db,donor['id'],donor['account_id'],DismantlingAction(ids=[row['id']],action='receipt'))
                db.commit();return result['updated']
            except HTTPException as exc:
                db.rollback();assert exc.status_code==409;return 0
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(run_action,['exclude','receipt']))
    stored=next(r for r in view(logged,donor)['items'] if r['id']==row['id'])
    assert stored['included'] is False
    parts=logged.get('/api/v1/parts').json()['items']
    assert sum(p['quantity'] for p in parts) in (0,1)
    assert bool(stored['received_at'])==bool(parts)


def test_invalid_hierarchy_and_fitment_do_not_import(logged,donor):
    path='/api/v1/dismantling/catalog/import';payload=catalog(2)
    payload['types'][1]['category_name']='Conflicting name'
    assert logged.post(path,json=payload).status_code==422
    payload=catalog();payload['types'][0]['compatible_with']='XC90 2010'
    assert logged.post(path,json=payload).status_code==422
    assert logged.post(base(donor)+'/start').json()['created']==0
    assert post(logged,donor,'/plan',{'included':False,'category_key':'body'}).status_code==422


def test_long_import_keys_can_be_received_without_database_overflow(logged,donor):
    payload=catalog();payload['types'][0].update(category_key='c'*100,subcategory_key='s'*100)
    assert logged.post('/api/v1/dismantling/catalog/import',json=payload).status_code==200
    logged.post(base(donor)+'/start')
    row=next(r for r in view(logged,donor)['items'] if r['catalog_key']=='test-0')
    post(logged,donor,'/actions',{'ids':[row['id']],'action':'dismantled'})
    assert post(logged,donor,'/actions',{'ids':[row['id']],'action':'receipt'}).status_code==200


def test_combined_stock_name_is_validated_before_catalog_import(logged,donor):
    payload=catalog();payload['types'][0].update(name='x'*200,position='left')
    assert logged.post('/api/v1/dismantling/catalog/import',json=payload).status_code==422
    assert logged.post(base(donor)+'/start').json()['created']==0


def test_replayed_bulk_receipt_cannot_receive_new_candidates_with_same_count(logged,donor):
    rows=view(logged,donor)['items'];first,second=rows[:2]
    post(logged,donor,'/actions',{'ids':[first['id']],'action':'dismantled'})
    before=view(logged,donor)
    request={'action':'receipt','expected_count':1,'selection_token':before['scope_tokens']['receipt']}
    assert post(logged,donor,'/batch',request).json()['updated']==1
    post(logged,donor,'/actions',{'ids':[second['id']],'action':'dismantled'})
    assert post(logged,donor,'/batch',request).status_code==409
    assert logged.get('/api/v1/parts').json()['total']==1
