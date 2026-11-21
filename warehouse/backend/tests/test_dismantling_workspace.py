"""Existing donor workspace, local test PostgreSQL only; no supplier requests."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.main import app
from app.models import DismantlingItem,Part,Operation,Vehicle
from app.services import assemblies
from tests.test_assemblies import group,feature,change,preview,inspect_node


def add_candidates(g):
    with Session(engine()) as db:
        ids=[]
        for i,status in enumerate(('present','damaged','unchecked','absent')):
            n=DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],source='manual.synthetic',catalog_key='bulk-'+str(i),category_key='body',category_name='Кузов',subcategory_key='door',subcategory_name='Двері',name='Перевірка '+status,quantity=1,status='damaged' if status=='damaged' else 'absent' if status=='absent' else 'unchecked',condition='damaged' if status=='damaged' else 'used',plan_v3={'inspection':'present' if status=='damaged' else status})
            db.add(n);db.flush();ids.append(n.id)
        db.commit()
    return ids


def report(c,g,damaged=False):
    r=c.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/receipt-preview",params={'include_damaged':str(damaged).lower()})
    assert r.status_code==200,r.text
    return r.json()


def payload(p):return dict(action='receipt_bulk',request_key=str(uuid4()),token=p['token'],include_damaged=p['include_damaged'],confirm_physical=True)


def test_workspace_flag_off_basic_actions_stay_available(logged,group,monkeypatch):
    g=group;ids=add_candidates(g);monkeypatch.setenv('ASSEMBLY_INVENTORY_ENABLED','false')
    assert logged.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/readiness").json()==dict(enabled=False,workspace_enabled=True)
    assert change(logged,g,'attach',item_id=g['nodes'][1],parent_id=g['nodes'][0]).status_code==404
    p=report(logged,g);assert len(p['eligible'])==1 and len(p['skipped'])==16
    response=logged.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p));assert response.status_code==200,response.text
    assert len(response.json()['received'])==1
    with Session(engine()) as db:
        assert db.get(DismantlingItem,ids[1]).part_id is None
        assert db.get(DismantlingItem,ids[2]).part_id is None
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='sale'))==0


def test_bulk_damage_explicit_replay_stale_and_no_duplicates(logged,group):
    g=group;ids=add_candidates(g);p=report(logged,g,True)
    assert len(p['eligible'])==2
    url=f"/api/v1/vehicles/{g['vehicle']}/assemblies";body=payload(p)
    r=logged.post(url,json=body);assert r.status_code==200,r.text
    assert logged.post(url,json=body).json()==r.json()
    assert logged.post(url,json={**body,'request_key':str(uuid4())}).status_code==409
    assert not report(logged,g,True)['eligible']
    with Session(engine()) as db:
        assert db.get(Part,db.get(DismantlingItem,ids[1]).part_id).condition=='damaged'
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==2
        assert db.scalar(select(func.count()).select_from(Part))==15


def test_bulk_atomic_rollback_on_mid_batch_failure(logged,group,monkeypatch):
    g=group;ids=add_candidates(g);p=report(logged,g,True);original=assemblies.receive_root;calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise HTTPException(409,'Synthetic second-row conflict')
        return original(*args,**kwargs)
    monkeypatch.setattr(assemblies,'receive_root',fail)
    r=logged.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p));assert r.status_code==409
    with Session(engine()) as db:
        assert all(db.get(DismantlingItem,id).part_id is None for id in ids)
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==0
        assert db.scalar(select(func.count()).select_from(Part))==13


def test_bulk_concurrent_commands_one_receipt(logged,group):
    g=group;add_candidates(g);p=report(logged,g)
    def send(_):
        with TestClient(app) as c:
            c.cookies.update(logged.cookies);c.headers.update(logged.headers)
            return c.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p)).status_code
    with ThreadPoolExecutor(2) as pool:assert sorted(pool.map(send,range(2)))==[200,409]
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==1


def test_bulk_csrf_workspace_and_required_confirmation(logged,group):
    from conftest import signup
    g=group;add_candidates(g);p=report(logged,g)
    with TestClient(app) as c:
        signup(c,'other-bulk@example.test')
        assert c.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/receipt-preview").status_code==404
        assert c.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p)).status_code==404
    assert logged.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json={**payload(p),'confirm_physical':False}).status_code==422
    with TestClient(app) as c:
        c.cookies.update(logged.cookies)
        assert c.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p)).status_code==403


def test_bulk_excludes_attached_children(logged,group):
    g=group;add_candidates(g)
    assert change(logged,g,'attach',item_id=g['nodes'][1],parent_id=g['nodes'][0]).status_code==200
    p=report(logged,g,True)
    assert next(n for n in p['skipped'] if n['id']==g['nodes'][1])['reason']=='У складі вузла'


def test_read_only_employee_cannot_preview_or_execute_receipt(logged,group,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    from tests.test_team import employee,activate
    g=group;add_candidates(g);p=report(logged,g)
    _,data=employee(logged,permissions=['vehicles.view','inventory.view'])
    c=activate(data)
    try:
        assert c.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies").status_code==200
        assert c.get(f"/api/v1/vehicles/{g['vehicle']}/assemblies/receipt-preview").status_code==403
        assert c.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p)).status_code==403
    finally:c.close()


def test_bulk_bounded_packages_and_no_source_requests(logged,group,monkeypatch):
    from app.services.unified_catalogue import CatalogueAdapter
    monkeypatch.setattr(CatalogueAdapter,'plan',lambda *a,**k:pytest.fail('No catalogue/API request allowed'))
    g=group
    with Session(engine()) as db:
        for i in range(105):db.add(DismantlingItem(account_id=g['account'],vehicle_id=g['vehicle'],source='manual.synthetic',catalog_key=f'package-{i}',category_key='engine',category_name='Двигун',subcategory_key='filter',subcategory_name='Фільтри',name=f'Пакет {i}',quantity=1,plan_v3={'inspection':'present'}))
        db.commit()
    p=report(logged,g);assert len(p['eligible'])==100
    assert sum(n['reason'].startswith('Наступний пакет') for n in p['skipped'])==5
    r=logged.post(f"/api/v1/vehicles/{g['vehicle']}/assemblies",json=payload(p));assert r.status_code==200,r.text
    assert len(r.json()['received'])==100
    assert len(report(logged,g)['eligible'])==5
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==100
