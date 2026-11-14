"""Release regressions: audit integrity/batching, etag compatibility and real restart safety."""
import threading,json,hashlib
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from sqlalchemy import select,text,event,inspect
from sqlalchemy.orm import Session
from app.db import engine
from app.main import app
from app.models import DismantlingItem,Operation,Part
from app.services.inventory import snapshot
from app.services.catalogue_format import digest
from app.services.vehicle_configuration import basis
from app.services import dismantling_plan_v3 as managed
from test_dismantling_plan_v3 import platform,preview,save,get,decision
from test_dismantling_preview import setup_vehicle
from test_canonical_v3 import market,build,item

def all_tables(db):
    return {t:hashlib.sha256(json.dumps(sorted(json.dumps(dict(r),sort_keys=True,default=str) for r in db.execute(text('SELECT * FROM "'+t+'"')).mappings())).encode()).hexdigest() for t in inspect(db.bind).get_table_names()}

def test_batch_preserves_each_audit_and_avoids_per_row_flush(platform,vehicle,part):
    setup_vehicle(vehicle);p=preview(platform,vehicle)
    with Session(engine()) as db:before=snapshot(db.get(Part,part['id']))
    flushes=[]
    def track(*args):flushes.append(1)
    event.listen(Session,'before_flush',track)
    try:
        r=save(platform,vehicle,p);assert r.status_code==200,r.text
        assert len(flushes)==2
        flushes.clear();ids=[i['id'] for i in get(platform,vehicle)['items']]
        assert decision(platform,vehicle,ids,'exclude',reason='Explicit entire synthetic category review').status_code==200
        assert len(flushes)==2
    finally:event.remove(Session,'before_flush',track)
    with Session(engine()) as db:
        binds=list(db.scalars(select(Operation).where(Operation.type=='dismantling_v3_bind')))
        decisions=list(db.scalars(select(Operation).where(Operation.type=='dismantling_v3_decision')))
        assert len(binds)==len(decisions)==33
        for op in binds:
            assert op.after['created_at'] and op.after['id']==op.entity_id and op.after['plan_v3']['placement_id']
            assert op.actor_id==op.account_id and op.after['actor_identity']['id']==op.actor_id
        for op in decisions:assert op.before['included'] is True and op.after['included'] is False
        assert before==snapshot(db.get(Part,part['id']))


def test_nonfinancial_etag_projection_has_stable_json_bytes(platform,vehicle,part):
    from app.models import Vehicle
    setup_vehicle(vehicle);save(platform,vehicle,preview(platform,vehicle))
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);rows=managed.rows_for(db,v)
        parts=list(db.scalars(select(Part).where(Part.account_id==v.account_id,Part.vehicle_id==v.id).order_by(Part.id)))
        ops=list(db.scalars(select(Operation.id).where(Operation.account_id==v.account_id,Operation.vehicle_id==v.id).order_by(Operation.id)))
        original=digest(jsonable_encoder([v.vin_details,v.engine_code,v.drive_type,v.id,v.account_id,basis(v),v.archived,v.dismantling_v3,[snapshot(r) for r in rows],[{k:getattr(p,k) for k in managed.PART_STATE_FIELDS} for p in parts],ops]))
        assert managed.state(db,v,rows)==original
        assert managed.state(db,v,rows)==original  # repeat serialization is byte-stable
        p=db.get(Part,part['id']);p.unit_cost=p.unit_cost+1;db.flush()
        assert managed.state(db,v,rows)==original
        v.engine_code='NEW-VERIFIED-CODE';db.flush()
        assert managed.state(db,v,rows)!=original


def test_repeated_actual_startup_with_worker_has_no_automatic_apply(platform,vehicle,monkeypatch):
    from app import staging
    import app.services.catalogue_jobs as catalogue_jobs
    import app.services.canonical_jobs as canonical_jobs
    setup_vehicle(vehicle);market(platform,[item()]);build(platform);save(platform,vehicle,preview(platform,vehicle))
    ids=[i['id'] for i in get(platform,vehicle)['items'][:2]]
    decision(platform,vehicle,[ids[0]],'exclude',reason='Persist across process lifecycle')
    decision(platform,vehicle,[ids[1]],'present');decision(platform,vehicle,[ids[1]],'dismantled',confirm=True);decision(platform,vehicle,[ids[1]],'receipt',confirm=True)
    with Session(engine()) as db:before=all_tables(db)
    catalogue_seen=threading.Event();canonical_seen=threading.Event()
    real_catalogue=catalogue_jobs.process_one;real_canonical=canonical_jobs.process_one
    def catalogue(*a,**kw):
        result=real_catalogue(*a,**kw);catalogue_seen.set();return result
    def canonical(*a,**kw):
        result=real_canonical(*a,**kw);canonical_seen.set();return result
    monkeypatch.setattr(catalogue_jobs,'process_one',catalogue);monkeypatch.setattr(canonical_jobs,'process_one',canonical)
    monkeypatch.setenv('WAREHOUSE_CATALOGUE_WORKER_ENABLED','true')
    for _ in range(2):
        staging.migrate(timeout=10)
        catalogue_seen.clear();canonical_seen.clear()
        with TestClient(app) as c:
            assert catalogue_seen.wait(5) and canonical_seen.wait(5)
            assert c.get('/health').status_code==200
        with Session(engine()) as db:assert before==all_tables(db)


def test_upgrade_from_staging_revision_preserves_real_A_and_populated_business_data(platform,vehicle,part,tmp_path):
    import os, sys, subprocess
    from app.services.aleto_import import BUNDLED_PACKAGE
    from test_catalogue_v2 import plan, upload, confirm
    from app.models.catalogue import CatalogueOffer, CatalogueApplication, CataloguePath
    from app.models.canonical import CanonicalType
    from sqlalchemy import func
    from uuid import uuid4
    j = plan(platform, upload(platform, raw=BUNDLED_PACKAGE.read_bytes(), filename=BUNDLED_PACKAGE.name))
    from test_catalogue_v2 import review_fixture
    j=review_fixture(platform,j)
    confirm(platform, j)
    setup_vehicle(vehicle)
    assert platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start").status_code == 200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations", json={'type': 'receipt', 'quantity': 5, 'reason': 'Populated migration fixture'}).status_code == 200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations", json={'type': 'reserve', 'quantity': 1, 'reason': 'Persist reservation'}).status_code == 200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations", json={'type': 'sale', 'quantity': 1, 'sale_price': '73.25', 'sale_currency': 'USD', 'request_key': str(uuid4())}).status_code == 200
    with Session(engine()) as db:
        first = db.scalar(select(DismantlingItem))
        first.included = False
        db.commit()
        excluded = first.id
    from historical_db import assert_historical_upgrade
    def verify(c,ids):
        assert [c.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('catalogue_offers','catalogue_applications','catalogue_paths')]==[7246,10112,14400]
        assert c.execute('SELECT count(*) FROM canonical_types').fetchone()==(0,)
        assert c.execute('SELECT included FROM dismantling_items WHERE id=%s',(excluded,)).fetchone()==(False,)
        assert c.execute("SELECT count(*) FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace AND NOT convalidated").fetchone()==(0,)
    assert_historical_upgrade('08b72c9d4e16',verify=verify)


def test_plan_etag_is_not_a_private_cost_guessing_oracle(platform,vehicle,part,monkeypatch):
    """A read-only employee must not validate hidden cost guesses using public data."""
    from test_team import employee,activate
    from app.services.vehicle_configuration import BASIS
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    _,data=employee(platform,['inventory.view','vehicles.view','catalog.view','audit.view']);c=activate(data)
    try:
        public_part=c.get('/api/v1/parts/'+part['id']).json()
        assert 'unit_cost' not in public_part
        public_vehicle=c.get('/api/v1/vehicles/'+vehicle['id']).json()
        operations=c.get('/api/v1/audit',params={'vehicle_id':vehicle['id'],'limit':200}).json()['items']
        ids=sorted(o['id'] for o in operations)
        fields={col.name for col in Part.__table__.columns}
        assert fields-set(public_part)=={'unit_cost'}
        template={k:v for k,v in public_part.items() if k in fields}
        observed=c.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3").json()['etag']
        matched=[]
        for amount in range(100):
            guessed={**template,'unit_cost':format(amount,'.2f')}
            candidate=digest([public_vehicle.get('vin_details'),public_vehicle.get('engine_code'),public_vehicle.get('drive_type'),public_vehicle['id'],public_vehicle['account_id'],digest({k:public_vehicle[k] for k in BASIS}),public_vehicle['archived'],public_vehicle['dismantling_v3'],[],[guessed],ids])
            if candidate==observed:matched.append(amount)
        assert not matched,'A low-permission user could validate a hidden financial value'
    finally:c.close()
