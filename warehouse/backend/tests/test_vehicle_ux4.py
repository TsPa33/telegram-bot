"""Donor list counts and targeted powertrain editing, no provider access."""
from sqlalchemy import event, text
from fastapi.testclient import TestClient
from app.main import app
from app.db import engine
from conftest import signup


def test_stock_counts_are_actual_positions_account_scoped_and_batched(logged,vehicle):
    other=logged.post('/api/v1/vehicles',json={'manufacturer':'BMW','model':'X3','year':2012}).json()
    zero=logged.post('/api/v1/parts',json={'name':'Zero position','vehicle_id':vehicle['id']}).json()
    active=logged.post('/api/v1/parts',json={'name':'Stock position','vehicle_id':vehicle['id']}).json()
    archived=logged.post('/api/v1/parts',json={'name':'Archived position','vehicle_id':vehicle['id']}).json()
    for p in (active,archived):
        assert logged.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'receipt','quantity':3,'reason':'Offline test stock'}).status_code==200
    assert logged.post('/api/v1/archive/parts/'+archived['id']).status_code==200
    with TestClient(app) as foreign:
        signup(foreign,'foreign-counts@example.test')
        v=foreign.post('/api/v1/vehicles',json={'manufacturer':'Volvo','model':'XC90','year':2010}).json()
        p=foreign.post('/api/v1/parts',json={'name':'Foreign stock','vehicle_id':v['id']}).json()
        foreign.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'receipt','quantity':1,'reason':'Foreign test'})
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(engine(),'before_cursor_execute',capture)
    try:rows=logged.get('/api/v1/vehicles').json()['items']
    finally:event.remove(engine(),'before_cursor_execute',capture)
    assert len(rows)==2
    assert {r['id']:r['stock_positions'] for r in rows}=={vehicle['id']:1,other['id']:0}
    assert len([s for s in statements if 'FROM parts' in s])==1
    assert logged.get('/api/v1/vehicles/'+vehicle['id']).json()['stock_positions']==1
    assert logged.post('/api/v1/vehicles/'+vehicle['id']+'/dismantling/prepare',json={}).status_code==200
    view=logged.get('/api/v1/vehicles/'+vehicle['id']+'/dismantling/workspace').json()
    assert view['stock_positions']==1 and view['counts']['total']==33
    logged.post('/api/v1/parts/'+active['id']+'/operations',json={'type':'sale','quantity':3,'reason':'Sold test stock'})
    assert logged.get('/api/v1/vehicles/'+vehicle['id']).json()['stock_positions']==0
    assert logged.get('/api/v1/parts/'+zero['id']).json()['quantity']==0


def test_powertrain_patch_preserves_identity_inventory_and_audit(logged,vehicle,part):
    url='/api/v1/vehicles/'+vehicle['id']
    before=logged.get(url).json()
    stock=logged.get('/api/v1/parts/'+part['id']).json()
    for values in ({'engine':'2.4 D5'},{'transmission':'Власна перевірена КПП'}):
        r=logged.patch(url+'/powertrain',json=values)
        assert r.status_code==200,r.text
        assert all(r.json()[k]==v for k,v in values.items())
        assert r.json()['id']==before['id'] and r.json()['number']==before['number']
        assert r.json()['donor_id']==before['donor_id'] and r.json()['notes']==before['notes']
    assert logged.get(url).json()['engine']=='2.4 D5'
    assert logged.get('/api/v1/vehicles').json()['items'][0]['transmission']=='Власна перевірена КПП'
    assert logged.get('/api/v1/parts/'+part['id']).json()==stock
    with engine().connect() as db:
        assert db.execute(text("SELECT count(*) FROM operations WHERE type='vehicle_update'")).scalar_one()==2
    assert logged.patch(url+'/powertrain',json={'engine':'2.4 D5'}).status_code==200
    with engine().connect() as db:
        assert db.execute(text("SELECT count(*) FROM operations WHERE type='vehicle_update'")).scalar_one()==2
    assert logged.patch(url+'/powertrain',json={'engine':''}).status_code==200
    assert logged.get(url).json()['engine']==''
    assert logged.get('/api/v1/vehicles').json()['total']==1
    ready=logged.get('/api/v1/vehicle-view/readiness').json()
    assert ready['contract_version']==4 and 'powertrain_edit' in ready['features']


def test_powertrain_auth_validation_and_history(logged,vehicle):
    url='/api/v1/vehicles/'+vehicle['id']
    assert logged.patch(url+'/powertrain',json={}).status_code==422
    for data in ({'engine':None},{'engine':'x'*101},{'transmission':'x'*51},{'number':99}):
        assert logged.patch(url+'/powertrain',json=data).status_code==422
    with TestClient(app) as other:
        assert other.patch(url+'/powertrain',json={'engine':'No'}).status_code==401
        signup(other,'other-powertrain@example.test')
        assert other.patch(url+'/powertrain',json={'engine':'No'}).status_code==404
    token=logged.headers.pop('X-CSRF-Token')
    assert logged.patch(url+'/powertrain',json={'engine':'No'}).status_code==403
    logged.headers['X-CSRF-Token']=token
    logged.put(url,json={k:vehicle[k] for k in ('manufacturer','model','year')}|{'ktype':9743})
    logged.patch(url+'/powertrain',json={'transmission':'Manual custom'})
    assert logged.get(url).json()['ktype']==9743
    logged.patch(url+'/powertrain',json={'engine':'Changed actual engine'})
    assert logged.get(url).json()['ktype'] is None
    assert logged.post('/api/v1/archive/vehicles/'+vehicle['id']).status_code==200
    assert logged.patch(url+'/powertrain',json={'engine':'No'}).status_code==404
