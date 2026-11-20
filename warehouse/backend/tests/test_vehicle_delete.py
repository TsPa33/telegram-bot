from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import DismantlingItem, Operation, Part, Photo, Vehicle, VehiclePhoto


def enable(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'is_staging', lambda: True)
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_NAME', 'warehouse-staging')


def test_delete_xc90_then_readd_vin_and_build_new_plan(logged, monkeypatch, tmp_path):
    enable(monkeypatch)
    monkeypatch.setenv('WAREHOUSE_PHOTO_DIR', str(tmp_path))
    data = {'manufacturer': 'Volvo', 'model': 'XC90', 'year': 2016,
            'vin': 'YV4A22PK2G1092943', 'donor_id': 'TEST-XC90-38'}
    created = logged.post('/api/v1/vehicles', json=data)
    assert created.status_code == 201, created.text
    vid = created.json()['id']
    base = f'/api/v1/vehicles/{vid}'
    assert logged.post(base+'/unified-catalogue/base').status_code == 200
    stock = logged.post('/api/v1/parts', json={'vehicle_id': vid, 'name': 'Тестова деталь'})
    assert stock.status_code == 201, stock.text
    part_id = stock.json()['id']
    assert logged.post(f'/api/v1/parts/{part_id}/operations',
                       json={'type': 'receipt', 'quantity': 1, 'reason': 'Fixture'}).status_code == 200
    with Session(engine()) as db:
        vehicle = db.get(Vehicle, vid)
        vehicle.number = 38
        account = vehicle.account_id
        db.add(VehiclePhoto(account_id=account, vehicle_id=vid, filename='donor.jpg', media_type='image/jpeg'))
        db.add(Photo(account_id=account, part_id=part_id, filename='part.jpg', media_type='image/jpeg'))
        old_rows = set(db.scalars(select(DismantlingItem.id).where(DismantlingItem.vehicle_id == vid)))
        db.commit()
    for filename in ('donor.jpg', 'part.jpg'):
        (tmp_path / filename).write_bytes(b'fixture photo')

    deleted = logged.delete(base)
    assert deleted.status_code == 204, deleted.text
    assert logged.get(base).status_code == 404
    assert not list(tmp_path.iterdir())
    with Session(engine()) as db:
        assert db.get(Part, part_id) is None
        assert db.scalar(select(func.count()).select_from(DismantlingItem)) == 0
        assert db.scalar(select(Operation).where(Operation.entity_id == vid)).type == 'vehicle_delete'

    replacement = logged.post('/api/v1/vehicles', json=data)
    assert replacement.status_code == 201, replacement.text
    new_id = replacement.json()['id']
    assert new_id != vid
    assert logged.post(f'/api/v1/vehicles/{new_id}/unified-catalogue/base').status_code == 200
    with Session(engine()) as db:
        new_rows = set(db.scalars(select(DismantlingItem.id).where(DismantlingItem.vehicle_id == new_id)))
        assert new_rows and new_rows.isdisjoint(old_rows)


def test_vehicle_delete_protects_sales_and_rolls_back(logged, part, monkeypatch):
    enable(monkeypatch)
    vid, part_id = part['vehicle_id'], part['id']
    with Session(engine()) as db:
        current = db.get(Part, part_id)
        db.add(Operation(account_id=current.account_id, actor_id=current.account_id,
                         vehicle_id=vid, part_id=part_id, entity_id=part_id,
                         entity_type='parts', type='sale', reason='Fixture sale',
                         before={}, after={}))
        db.commit()
    result = logged.delete(f'/api/v1/vehicles/{vid}')
    assert result.status_code == 409, result.text
    with Session(engine()) as db:
        assert db.get(Vehicle, vid) is not None
        assert db.get(Part, part_id) is not None
        assert db.scalar(select(Operation.id).where(Operation.type == 'sale'))


def test_vehicle_delete_scope_and_explicit_permission(logged, vehicle, monkeypatch):
    from tests.test_team import activate, employee

    path = f"/api/v1/vehicles/{vehicle['id']}"
    monkeypatch.setenv('WAREHOUSE_ENV', 'production')
    assert logged.delete(path).status_code in (403, 404)
    enable(monkeypatch)
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED', 'true')
    _, invite = employee(logged, permissions=['vehicles.view', 'vehicles.edit'])
    staff = activate(invite)
    try:
        assert staff.delete(path).status_code == 403
    finally:
        staff.close()
    _, invite = employee(logged, email='delete@example.test', permissions=['vehicles.delete'])
    manager = activate(invite)
    try:
        assert manager.delete(path).status_code == 204
    finally:
        manager.close()


def test_vehicle_delete_preserves_a_cross_donor_warehouse_link(logged, part, monkeypatch):
    enable(monkeypatch)
    source_id = part['vehicle_id']
    other = logged.post('/api/v1/vehicles', json={'manufacturer':'Volvo','model':'XC60','year':2018})
    assert other.status_code == 201, other.text
    other_id = other.json()['id']
    with Session(engine()) as db:
        account = db.get(Vehicle, other_id).account_id
        row = DismantlingItem(account_id=account, vehicle_id=other_id, part_id=part['id'],
                              source='test', catalog_key='cross-link', name='Linked',
                              category_key='test', category_name='Test',
                              subcategory_key='test', subcategory_name='Test')
        db.add(row)
        db.commit()
        row_id = row.id
    result = logged.delete(f'/api/v1/vehicles/{source_id}')
    assert result.status_code == 409, result.text
    with Session(engine()) as db:
        assert db.get(Vehicle, source_id) is not None
        assert db.get(Vehicle, other_id) is not None
        assert db.get(DismantlingItem, row_id).part_id == part['id']
