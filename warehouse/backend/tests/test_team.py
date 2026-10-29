"""Real local PostgreSQL, personal sessions, live permissions and tenant boundaries."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json,sys
from subprocess import run
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db import engine
from app.permissions import PERMISSIONS,DEFAULT_EMPLOYEE,route_permissions

@pytest.fixture(autouse=True)
def explicitly_enable_creation_in_team_tests(monkeypatch):
    # Ordinary runs remain disabled; these tests exercise the explicit Stage 4 flag.
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')

TEMP='temporary-worker-password'
PASSWORD='personal-worker-new-password'

def employee(owner,permissions=None,role='MANAGER',email=None):
    data={'name':'Працівник Іван','email':email or str(uuid4())+'@example.test','password':TEMP,'role':role,'permissions':DEFAULT_EMPLOYEE if permissions is None else permissions}
    r=owner.post('/api/v1/team',json=data);assert r.status_code==201,r.text
    return r.json(),data

def login(client,data,password=PASSWORD):
    r=client.post('/api/v1/auth/login',json={'email':data['email'],'password':password});assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf_token'];return r

def activate(data):
    c=TestClient(app);login(c,data,TEMP)
    assert c.get('/api/v1/parts').status_code==403
    r=c.post('/api/v1/auth/password',json={'current_password':TEMP,'password':PASSWORD});assert r.status_code==200,r.text
    assert c.get('/api/v1/auth/me').status_code==401
    login(c,data);return c

def patch(owner,row,**changes):
    body={k:row[k] for k in ('name','role','permissions','is_active')};body.update(changes)
    return owner.patch('/api/v1/team/'+row['id'],json=body)

def op(c,part,type='sale',key=None,**kwargs):
    return c.post('/api/v1/parts/'+part['id']+'/operations',json={'type':type,'quantity':1,'request_key':key or str(uuid4()),'sale_price':'12.34','sale_currency':'USD',**kwargs})

def test_owner_and_activation_blocking_revocation(logged,part):
    info=logged.get('/api/v1/auth/me').json();assert info['role']=='DIRECTOR' and set(info['permissions'])==set(PERMISSIONS)
    row,data=employee(logged);c=activate(data)
    try:
        assert c.get('/api/v1/parts').json()['items'][0]['id']==part['id']
        assert op(c,part).status_code==403
        assert patch(logged,row,permissions=[]).status_code==200
        assert c.get('/api/v1/parts').status_code==403
        assert patch(logged,row,is_active=False).status_code==200
        assert c.get('/api/v1/auth/me').status_code==401
        assert c.post('/api/v1/auth/login',json={'email':data['email'],'password':PASSWORD}).status_code==401
        assert patch(logged,row,is_active=True).status_code==200
        login(c,data);assert c.get('/api/v1/parts').status_code==200
        assert logged.post('/api/v1/team/'+row['id']+'/reset-password',json={'password':'new-temporary-access-password'}).status_code==200
        assert c.get('/api/v1/auth/me').status_code==401
        events=logged.get('/api/v1/team/events').json();serialized=json.dumps(events)
        assert TEMP not in serialized and PASSWORD not in serialized and 'password_hash' not in serialized
    finally:c.close()


def test_admin_cannot_escalate_self_director_or_manager(logged):
    rights=DEFAULT_EMPLOYEE+['team.view','team.manage_managers']
    admin,data=employee(logged,rights,'ADMIN');c=activate(data)
    try:
        manager,_=employee(logged)
        assert c.post('/api/v1/team',json={'name':'Another','email':'admin2@example.test','password':TEMP,'role':'ADMIN','permissions':rights}).status_code==403
        assert c.post('/api/v1/team',json={'name':'Another','email':'manager2@example.test','password':TEMP,'permissions':['sales.create']}).status_code==403
        assert patch(c,admin,permissions=rights+['sales.create']).status_code in (403,404)
        owner=logged.get('/api/v1/auth/me').json()
        assert c.patch('/api/v1/team/'+owner['id'],json={'name':'Hacked','role':'MANAGER','permissions':[],'is_active':False}).status_code==404
        assert patch(c,manager,is_active=False).status_code==200
        higher,_=employee(logged,DEFAULT_EMPLOYEE+['sales.create'])
        assert patch(c,higher,is_active=False).status_code==200
        assert c.post('/api/v1/team/'+higher['id']+'/reset-password',json={'password':TEMP}).status_code==403
        assert patch(c,higher,permissions=higher['permissions']+['parts.change_price']).status_code==403
        allowed=c.post('/api/v1/team',json={'name':'Delegated','email':'delegated@example.test','password':TEMP,'permissions':DEFAULT_EMPLOYEE})
        assert allowed.status_code==201,allowed.text
    finally:c.close()


def test_financial_redaction_actor_replay_and_smart_tenant(logged,part):
    logged.patch('/api/v1/parts/'+part['id']+'/price',json={'selling_price':'99.99','currency':'USD'})
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':3,'reason':'Team stock'}).status_code==200
    rights=DEFAULT_EMPLOYEE+['sales.create','sales.view','audit.view','analytics.view','parts.notes','parts.inspect','inventory.edit']
    row,data=employee(logged,rights);c=activate(data)
    other,data2=employee(logged,rights);c2=activate(data2)
    try:
        key=str(uuid4());assert op(c,part,key=key).status_code==200;assert op(c,part,key=key).status_code==200
        assert op(c2,part,key=key).status_code==409
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==2
        audit=logged.get('/api/v1/audit',params={'type':'sale'}).json()['items']
        assert len(audit)==1 and audit[0]['actor_id']==row['id'] and audit[0]['after']['sale']['actor_name']==row['name']
        for path in ['/parts','/parts/'+part['id'],'/smart-search/parts?q=Test','/sales','/audit','/dashboard','/archive?entity=parts']:
            r=c.get('/api/v1'+path)
            if path.startswith('/archive'):assert r.status_code==403;continue
            assert r.status_code==200,(path,r.text)
            encoded=r.json()
            def check(v):
                if isinstance(v,list):
                    for x in v:check(x)
                if isinstance(v,dict):
                    for k,x in v.items():
                        assert k not in ('unit_cost','acquisition_cost','sale','unit_price','line_total','allocated_parts_cost','potential_gross_margin'),(path,k)
                        check(x)
            check(encoded)
        assert c.put('/api/v1/parts/'+part['id'],json={'name':'Changed','unit_cost':'0.00'}).status_code==403
        assert c.put('/api/v1/parts/'+part['id'],json={'name':'Changed'}).status_code==200
        assert logged.get('/api/v1/parts/'+part['id']).json()['unit_cost']=='20.00'
        assert c.patch('/api/v1/parts/'+part['id']+'/notes',json={'internal_notes':'One','expected_notes':''}).status_code==200
        assert c2.patch('/api/v1/parts/'+part['id']+'/notes',json={'internal_notes':'Two','expected_notes':''}).status_code==409
        assert c.patch('/api/v1/parts/'+part['id']+'/inspection',json={'condition':'damaged'}).status_code==200
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==2
        assert patch(logged,row,permissions=DEFAULT_EMPLOYEE).status_code==200
        assert op(c,part,key=key).status_code==403
        with TestClient(app) as foreign:
            from conftest import signup
            signup(foreign,'foreign-workspace@example.test')
            p=foreign.post('/api/v1/parts',json={'name':'Secret Other Company'}).json()
            assert c.get('/api/v1/parts/'+p['id']).status_code==404
            assert c.get('/api/v1/smart-search/parts',params={'q':'Secret Other Company'}).json()['total']==0
    finally:c.close();c2.close()


def test_two_employees_cannot_sell_last_unit_twice(logged,part):
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':1,'reason':'Last unit'}).status_code==200
    clients=[]
    try:
        for _ in range(2):
            _,data=employee(logged,DEFAULT_EMPLOYEE+['sales.create']);clients.append(activate(data))
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda c:op(c,part).status_code,clients))
        assert sorted(codes)==[200,409]
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==0
        assert logged.get('/api/v1/audit?type=sale').json()['total']==1
    finally:
        for c in clients:c.close()


def test_migration_preserves_populated_history_and_owners(logged,part):
    with engine().connect() as db:
        parts=db.execute(text('SELECT row_to_json(p) FROM parts p ORDER BY id')).scalars().all()
        operations=db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()
        ids=db.execute(text('SELECT id,email,password_hash FROM accounts ORDER BY id')).all()
    assert run([sys.executable,'-m','alembic','downgrade','a73e05b9c842'],capture_output=True).returncode==0
    assert run([sys.executable,'-m','alembic','upgrade','head'],capture_output=True).returncode==0
    with engine().connect() as db:
        assert db.execute(text('SELECT row_to_json(p) FROM parts p ORDER BY id')).scalars().all()==parts
        assert db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()==operations
        assert db.execute(text('SELECT id,email,password_hash FROM accounts ORDER BY id')).all()==ids
        assert db.scalar(text("SELECT count(*) FROM accounts WHERE role<>'DIRECTOR' OR workspace_account_id IS NOT NULL"))==0
    assert run([sys.executable,'-m','alembic','check'],capture_output=True).returncode==0
    for path,version in [('sales-workspace',5),('orders',6),('workshop',7),('smart-search',8),('team',9)]:
        result=logged.get('/api/v1/'+path+'/readiness');assert result.status_code==200,result.text
        assert result.json()['contract_version']==version
    employee(logged)
    assert run([sys.executable,'-m','alembic','downgrade','a73e05b9c842'],capture_output=True).returncode!=0
    assert logged.get('/api/v1/team/readiness').status_code==200


def authenticated_routes(routes=None):
    # FastAPI 0.143 keeps included routers lazy; app.routes alone is not flat.
    for route in app.routes if routes is None else routes:
        if hasattr(route,'original_router'):
            yield from authenticated_routes(route.original_router.routes)
        elif hasattr(route,'dependant') and any(dep.call.__name__=='identity' for dep in route.dependant.dependencies):
            yield from ((method,route.path) for method in route.methods)


def test_every_authenticated_route_has_a_policy():
    reviewed=list(authenticated_routes())
    assert len(reviewed)>50,'Route discovery must not silently become vacuous'
    for method,path in reviewed:
        permissions=route_permissions(method,path,{'type':'sale','action':'receipt','_route_action':'sell'})
        assert '__deny__' not in permissions,(method,path)
        assert set(permissions)<=PERMISSIONS.keys()


def test_password_validation_does_not_echo_secret(logged):
    response=logged.post('/api/v1/team',json={'name':'Worker','email':'worker@example.test','password':'shortSecret'})
    assert response.status_code==422
    assert 'shortSecret' not in response.text and '"input"' not in response.text
    row,_=employee(logged)
    spaced=' password-with-leading-space'
    r=logged.post('/api/v1/team/'+row['id']+'/reset-password',json={'password':spaced})
    assert r.status_code==422 and spaced not in r.text


def test_staff_orders_use_workspace_and_real_actor(logged,part):
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':2,'reason':'Team order stock'}).status_code==200
    rights=DEFAULT_EMPLOYEE+['orders.create','orders.view','orders.edit','orders.fulfill','sales.create']
    row,data=employee(logged,rights);c=activate(data)
    try:
        buyer=c.post('/api/v1/buyers',json={'name':'Покупець','phone':'+380501234567'});assert buyer.status_code==201,buyer.text
        key=str(uuid4());payload={'request_key':key,'buyer_id':buyer.json()['id'],'lines':[{'part_id':part['id'],'quantity':1,'unit_price':'42.01','currency':'UAH'}],'delivery_method':'pickup'}
        result=c.post('/api/v1/orders',json=payload);assert result.status_code==201,result.text
        order=result.json();assert order['account_id']==logged.get('/api/v1/auth/me').json()['id']
        assert 'unit_price' not in order['lines'][0] and 'totals_by_currency' not in order
        for action in ['reserve','sell']:
            r=c.post('/api/v1/orders/'+order['id']+'/'+action,json={'request_key':str(uuid4())});assert r.status_code==200,r.text
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==1
        events=logged.get('/api/v1/orders/'+order['id']+'/events').json()['items'];assert events and all(e['actor_id']==row['id'] for e in events)
        sales=logged.get('/api/v1/audit?type=sale').json()['items'];assert len(sales)==1 and sales[0]['actor_id']==row['id']
        assert patch(logged,row,permissions=DEFAULT_EMPLOYEE).status_code==200
        assert c.post('/api/v1/orders',json=payload).status_code==403
    finally:c.close()


def test_controlled_team_enablement_fails_closed(logged,monkeypatch):
    monkeypatch.setattr('app.services.team.creation_enabled',lambda:False)
    assert logged.get('/api/v1/team/readiness').json()['employee_creation_enabled'] is False
    r=logged.post('/api/v1/team',json={'name':'Not enabled','email':'not-enabled@example.test','password':TEMP})
    assert r.status_code==403
    assert logged.get('/api/v1/team').json()['total']==1


def test_concurrent_employee_prices_keep_both_audit_actors(logged,part):
    clients=[];ids=[]
    try:
        for _ in range(2):
            row,data=employee(logged,DEFAULT_EMPLOYEE+['parts.change_price']);ids.append(row['id']);clients.append(activate(data))
        def update(index):return clients[index].patch('/api/v1/parts/'+part['id']+'/price',json={'selling_price':str(70+index*10)+'.00','currency':'UAH'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(update,[0,1]))==[200,200]
        stored=logged.get('/api/v1/parts/'+part['id']).json();assert stored['selling_price'] in ('70.00','80.00') and stored['quantity']==0
        events=logged.get('/api/v1/audit?type=part_update').json()['items'];assert len(events)==2 and {e['actor_id'] for e in events}==set(ids)
    finally:
        for c in clients:c.close()


def test_concurrent_employee_orders_share_numbering_not_identity(logged,part):
    buyer=logged.post('/api/v1/buyers',json={'name':'Покупець','phone':'+380501234567'}).json();clients=[];ids=[]
    try:
        for _ in range(2):
            row,data=employee(logged,DEFAULT_EMPLOYEE+['orders.create','orders.view']);ids.append(row['id']);clients.append(activate(data))
        def create(index):
            r=clients[index].post('/api/v1/orders',json={'request_key':str(uuid4()),'buyer_id':buyer['id'],'lines':[{'part_id':part['id'],'quantity':1,'unit_price':'40.00','currency':'UAH'}],'delivery_method':'pickup'})
            assert r.status_code==201,r.text
            return r.json()
        with ThreadPoolExecutor(max_workers=2) as pool:orders=list(pool.map(create,[0,1]))
        assert {o['number'] for o in orders}=={1,2}
        assert len({o['account_id'] for o in orders})==1
        for index,order in enumerate(orders):
            events=logged.get('/api/v1/orders/'+order['id']+'/events').json()['items'];assert all(e['actor_id']==ids[index] for e in events)
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==0
    finally:
        for c in clients:c.close()


def test_analytics_does_not_bypass_audit_or_finance_permissions(logged,part):
    _,data=employee(logged,DEFAULT_EMPLOYEE+['analytics.view']);c=activate(data)
    try:
        result=c.get('/api/v1/dashboard');assert result.status_code==200
        body=result.json()
        assert body['positions']==1
        assert not {'recent_operations','estimated_sales_value','valuation_by_currency','allocated_parts_cost','potential_gross_margin','by_vehicle'}&body.keys()
        assert c.get('/api/v1/audit').status_code==403
        assert c.post('/api/v1/auth/logout').status_code==204
        assert c.get('/api/v1/auth/me').status_code==401
    finally:c.close()


def test_employee_photos_are_scoped_and_audited(logged,part,tmp_path,monkeypatch):
    from io import BytesIO
    from PIL import Image
    monkeypatch.setenv('WAREHOUSE_PHOTO_DIR',str(tmp_path))
    row,data=employee(logged,DEFAULT_EMPLOYEE+['inventory.edit']);c=activate(data)
    try:
        image=BytesIO();Image.new('RGB',(4,4),'white').save(image,format='PNG')
        result=c.post('/api/v1/parts/'+part['id']+'/photos',files={'file':('sample.png',image.getvalue(),'image/png')});assert result.status_code==201,result.text
        url=result.json()['url'];assert c.get(url).status_code==200
        events=logged.get('/api/v1/audit?type=photo_create').json()['items'];assert len(events)==1 and events[0]['actor_id']==row['id'] and events[0]['part_id']==part['id']
        assert patch(logged,row,permissions=[]).status_code==200
        assert c.get(url).status_code==403
        with TestClient(app) as foreign:
            from conftest import signup
            signup(foreign,'photo-foreign-team@example.test');assert foreign.get(url).status_code==404
    finally:c.close()


def test_restricted_full_editor_preserves_hidden_links_and_metadata(logged,part):
    original=logged.get('/api/v1/parts/'+part['id']).json()
    _,data=employee(logged,['inventory.view','inventory.edit']);c=activate(data)
    try:
        result=c.put('/api/v1/parts/'+part['id'],json={'name':'Safe renamed part'});assert result.status_code==200,result.text
        stored=logged.get('/api/v1/parts/'+part['id']).json()
        for field in ('vehicle_id','category_id','subcategory_id','unit_cost','selling_price','currency','location','condition','availability','internal_notes','quantity'):
            assert stored[field]==original[field],field
        assert c.put('/api/v1/parts/'+part['id'],json={'name':'Unsafe','vehicle_id':None}).status_code==403
    finally:c.close()


@pytest.mark.parametrize('mode', ['development', 'staging', 'production'])
def test_creation_requires_explicit_flag_in_every_environment(logged, monkeypatch, mode):
    monkeypatch.setenv('WAREHOUSE_ENV', mode)
    monkeypatch.setenv('WAREHOUSE_PUBLIC_ORIGIN','https://warehouse-test.example')
    headers={'Origin':'https://warehouse-test.example'}
    monkeypatch.delenv('WAREHOUSE_TEAM_CREATION_ENABLED', raising=False)
    assert logged.get('/api/v1/team/readiness').json()['employee_creation_enabled'] is False
    body={'name':'Disabled by default','email':'default-off@example.test','password':TEMP}
    assert logged.post('/api/v1/team',json=body,headers=headers).status_code==403
    assert logged.get('/api/v1/team').json()['total']==1
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    assert logged.post('/api/v1/team',json=body,headers=headers).status_code==201


def test_admin_cannot_reactivate_manager_with_undelegatable_rights(logged):
    rights=DEFAULT_EMPLOYEE+['team.view','team.manage_managers']
    _,data=employee(logged,rights,'ADMIN');admin=activate(data)
    manager,_=employee(logged,DEFAULT_EMPLOYEE+['sales.create'])
    try:
        assert patch(logged,manager,is_active=False).status_code==200
        assert patch(admin,manager,is_active=True).status_code==403
        state=next(u for u in logged.get('/api/v1/team').json()['items'] if u['id']==manager['id'])
        assert state['is_active'] is False and 'sales.create' in state['permissions']
        assert patch(admin,manager,is_active=True,permissions=DEFAULT_EMPLOYEE).status_code==200
    finally:admin.close()


def test_login_serializes_with_password_reset_and_revokes_new_session(logged,monkeypatch):
    from threading import Event
    from concurrent.futures import TimeoutError
    from app.services import auth
    row,data=employee(logged);worker=activate(data);worker.close()
    entered=Event();release=Event();reset_started=Event()
    verify=auth.hasher.verify
    def pause_verify(self,*args,**kwargs):
        entered.set()
        assert release.wait(10),'login test coordination timeout'
        return verify(*args,**kwargs)
    monkeypatch.setattr(type(auth.hasher),'verify',pause_verify)
    newcomer=TestClient(app)
    def reset():
        reset_started.set()
        return logged.post('/api/v1/team/'+row['id']+'/reset-password',json={'password':'new-temporary-reset-password'})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(newcomer.post,'/api/v1/auth/login',json={'email':data['email'],'password':PASSWORD})
            assert entered.wait(5)
            resetting=pool.submit(reset);assert reset_started.wait(5)
            try:
                with pytest.raises(TimeoutError):resetting.result(timeout=.3)
            finally:release.set()
            assert future.result(timeout=10).status_code==200
            assert resetting.result(timeout=10).status_code==200
        assert newcomer.get('/api/v1/auth/me').status_code==401
    finally:release.set();newcomer.close()


def test_actor_cannot_be_spoofed_in_stock_payload(logged,part):
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':2,'reason':'Stock'}).status_code==200
    row,data=employee(logged,DEFAULT_EMPLOYEE+['sales.create']);worker=activate(data)
    try:
        owner=logged.get('/api/v1/auth/me').json()
        for field in ['actor_id','account_id','workspace_account_id']:
            response=op(worker,part,**{field:owner['id']})
            assert response.status_code==422,response.text
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==2
        assert op(worker,part).status_code==200
        event=logged.get('/api/v1/audit?type=sale').json()['items'][0]
        assert event['actor_id']==row['id'] and event['account_id']==owner['id']
    finally:worker.close()


def test_populated_upgrade_preserves_sessions_reserves_orders_and_failed_retry(logged,part):
    # All transitions affect only this disposable *_test database.
    # Seed priced sales, manual and order reservations, request caches and sessions.
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':7,'reason':'Migration regression'}).status_code==200
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'reserve','quantity':1,'reason':'Manual reserve','request_key':str(uuid4())}).status_code==200
    sale_key=str(uuid4())
    assert op(logged,part,key=sale_key,sale_price='0.01',sale_currency='USD').status_code==200
    buyer=logged.post('/api/v1/buyers',json={'name':'Migration buyer','phone':'0501234567'}).json()
    order_key=str(uuid4())
    created=logged.post('/api/v1/orders',json={'buyer_id':buyer['id'],'request_key':order_key,'lines':[{'part_id':part['id'],'quantity':1,'unit_price':'123.45','currency':'UAH'}]})
    assert created.status_code==201,created.text
    order=created.json()
    reserve=logged.post('/api/v1/orders/'+order['id']+'/reserve',json={'request_key':str(uuid4())})
    assert reserve.status_code==200,reserve.text
    tables=['vehicles','parts','operations','sessions','buyers','orders','order_lines','order_reservations','order_events','stock_requests','order_requests']
    def snapshot_tables():
        with engine().connect() as db:
            rows={table:db.execute(text(f'SELECT row_to_json(t) FROM {table} t')).scalars().all() for table in tables}
            # This roundtrip targets legacy business columns; the additive v3
            # header does not exist at the deliberately downgraded revision.
            for vehicle in rows['vehicles']:
                assert vehicle.pop('dismantling_v3',{})=={}
            # Stage3B defaults are absent on the deliberately old schema.
            # Validate every new default before comparing every legacy column.
            defaults={'assortment_enabled':True,'inventory_origin':'legacy','quantity_basis':'legacy','physical_location_kind':'unknown','canonical_placement_id':None,'activation_operation_id':None}
            for part in rows['parts']:
                for field,value in defaults.items():assert part.pop(field,value)==value
            return rows
    # Match by serialized immutable content rather than unspecified row ordering.
    def normalized(rows):return {t:sorted(json.dumps(r,sort_keys=True) for r in v) for t,v in rows.items()}
    before=snapshot_tables()
    for table in ['stock_requests','order_requests']:
        for row in before[table]:row.pop('actor_id')
    with engine().connect() as db:
        owners=db.execute(text('SELECT id,email,name,password_hash,created_at FROM accounts ORDER BY id')).all()
    assert run([sys.executable,'-m','alembic','downgrade','a73e05b9c842'],capture_output=True).returncode==0
    # Existing inventory rows lock DDL out. A failed migration must roll back,
    # retain the old revision, and be retryable with no partial role columns.
    with engine().begin() as locked:
        locked.execute(text('LOCK TABLE accounts IN SHARE MODE'))
        failed=run([sys.executable,'-m','alembic','upgrade','head'],capture_output=True,timeout=20)
        assert failed.returncode!=0
    with engine().connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='a73e05b9c842'
        assert not db.scalar(text("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='accounts' AND column_name='role')"))
    assert normalized(snapshot_tables())==normalized(before)
    for _ in range(2):assert run([sys.executable,'-m','alembic','upgrade','head'],capture_output=True).returncode==0
    after=snapshot_tables()
    for table in ['stock_requests','order_requests']:
        for row in after[table]:assert row.pop('actor_id')==row['account_id']
    assert normalized(after)==normalized(before)
    with engine().connect() as db:
        assert db.execute(text('SELECT id,email,name,password_hash,created_at FROM accounts ORDER BY id')).all()==owners
        assert db.scalar(text("SELECT count(*) FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace AND NOT convalidated"))==0
    # The exact pre-migration browser cookie and request keys still work.
    assert logged.get('/api/v1/auth/me').status_code==200
    assert op(logged,part,key=sale_key,sale_price='0.01',sale_currency='USD').status_code==200
    assert logged.get('/api/v1/orders/'+order['id']).json()['status']=='reserved'
    current=logged.get('/api/v1/parts/'+part['id']).json()
    assert current['quantity']==6 and current['reserved_quantity']==2
    assert logged.get('/api/v1/sales').json()['items'][0]['unit_price']=='0.01'
    assert run([sys.executable,'-m','alembic','check'],capture_output=True).returncode==0


def test_every_permission_protected_route_denies_employee_without_rights(logged,part):
    import re
    from app.route_registry import KNOWN_ROUTES
    _,data=employee(logged,[]);worker=activate(data)
    def counts():
        with engine().connect() as db:
            return {t:db.scalar(text(f'SELECT count(*) FROM {t}')) for t in ['accounts','vehicles','parts','operations','orders','stock_requests','order_requests','team_events']}
    before=counts();checked=[]
    try:
        authenticated=set(authenticated_routes())
        for method,path in sorted(KNOWN_ROUTES & authenticated):
            body={'type':'sale','action':'receipt'}
            rights=route_permissions(method,path,{**body,'_route_action':'sell'})
            if not rights:continue
            replacements={'id':part['id'],'item_id':str(uuid4()),'entity':'parts','action':'sell'}
            url=re.sub(r'\{([^}]+)\}',lambda m:replacements.get(m[1],str(uuid4())),path)
            response=worker.request(method,url,**({'json':body} if method not in ('GET','HEAD') else {}))
            assert response.status_code==403,(method,path,response.status_code,response.text)
            checked.append((method,path))
        assert len(checked)>50
        assert counts()==before
    finally:worker.close()


def test_waiting_mutation_does_not_revive_revoked_session(logged,part):
    from threading import Event
    from sqlalchemy import event
    _,data=employee(logged,DEFAULT_EMPLOYEE+['sales.create']);worker=activate(data)
    user=worker.get('/api/v1/auth/me').json()
    assert logged.post('/api/v1/parts/'+part['id']+'/operations',json={'type':'receipt','quantity':1,'reason':'Race regression'}).status_code==200
    waiting=Event()
    def observe(conn,cursor,statement,parameters,context,executemany):
        if 'FOR SHARE' in statement and 'accounts' in statement:waiting.set()
    event.listen(engine(),'before_cursor_execute',observe)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with engine().begin() as lock:
                lock.execute(text('SELECT id FROM accounts WHERE id=:id FOR UPDATE'),{'id':user['id']})
                pending=pool.submit(op,worker,part)
                assert waiting.wait(5),'employee mutation did not reach actor lock'
                lock.execute(text('DELETE FROM sessions WHERE account_id=:id'),{'id':user['id']})
            assert pending.result(timeout=10).status_code==401
        assert logged.get('/api/v1/parts/'+part['id']).json()['quantity']==1
        assert logged.get('/api/v1/audit?type=sale').json()['total']==0
    finally:event.remove(engine(),'before_cursor_execute',observe);worker.close()
