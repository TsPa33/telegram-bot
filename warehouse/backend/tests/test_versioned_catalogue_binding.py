from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.models import DismantlingItem, Operation, Part, Vehicle
from app.services.auto_oem import enrich_vehicle
from app.services.unified_catalogue import CatalogueAdapter, CatalogueUnavailable
from conftest import signup
from test_unified_catalogue import detail_items, envelope


@pytest.fixture
def catalogue_donor(logged, monkeypatch):
    entries = {
        car: dict(source_modification_id=car, model_id=13084, manufacturer_id=120,
                  manufacturer='Volvo', model='XC60 II', snapshot_sha=str(index)*64,
                  modification={'description': f'Variant {index}', 'constructioninterval': '2017 - 2025'})
        for index, car in enumerate((126480, 126481), 1)
    }
    failures = {}

    def directory(self, after=0, car_id=None, **kwargs):
        return {'items': [entry for car, entry in entries.items() if car_id in (None, car)]}

    def plan(self, car, **kwargs):
        if failures.get(car) == 'plan':
            raise CatalogueUnavailable('fixture_down')
        result = envelope(car)
        result['payload']['source_snapshot_sha'] = entries[car]['snapshot_sha']
        return result

    def articles(self, car, product, sha, **kwargs):
        if failures.get(car) == 'articles':
            raise CatalogueUnavailable('fixture_down')
        if failures.get(car) == 'partial':
            return []
        rows = detail_items()
        rows[0].update(car_id=car, oem=[{'manufacturerId': 120, 'OENbr': f'FIXTURE-{car}'}])
        return rows

    monkeypatch.setattr(CatalogueAdapter, 'directory', directory)
    monkeypatch.setattr(CatalogueAdapter, 'plan', plan)
    monkeypatch.setattr(CatalogueAdapter, 'articles', articles)

    response = logged.post('/api/v1/vehicles', json=dict(
        manufacturer='Volvo', model='XC60', year=2022, engine_variant='Variant 1'))
    assert response.status_code == 201, response.text
    donor = response.json()['id']
    url = f'/api/v1/vehicles/{donor}'
    with Session(engine()) as db:
        tenant = db.get(Vehicle, donor).account_id

    def enrich(account=tenant):
        return enrich_vehicle(engine(), account, donor)

    def state():
        return logged.get(url+'/global-dismantling').json()

    def selection(car, current):
        return dict(request_key=str(uuid4()), expected_basis=current['selection_basis'],
                    expected_selection_revision=current['selection_revision'],
                    **{key: entries[car][key] for key in (
                        'source_modification_id','model_id','manufacturer_id')},
                    source_snapshot_sha=entries[car]['snapshot_sha'])

    assert enrich() == 1
    stock = dict(keys=[state()['keys']['106']], confirm_physical_receipt=True)
    response = logged.post(url+'/unified-catalogue/stock', json=stock)
    assert response.json() == {'added': 1, 'skipped': 0}
    return url, enrich, state, selection, failures, stock


def physical_snapshot():
    with Session(engine()) as db:
        part = db.scalar(select(Part))
        row = db.scalar(select(DismantlingItem))
        receipts = db.scalars(select(Operation.id).where(Operation.type == 'receipt')).all()
        return (part.id, row.id, part.quantity, part.reserved_quantity, part.selling_price,
                row.status, row.received_at, receipts)


def test_switch_preserves_binding_receipt_and_manual_oem(logged, catalogue_donor):
    url, enrich, state, selection, _, stock = catalogue_donor
    original = physical_snapshot()
    part_id, item_id = original[:2]
    current = state()
    request = selection(126481, current)
    for _ in range(2):
        assert logged.post(url+'/catalogue-selection', json=request).status_code == 200
    enrich()
    current = state()
    assert current['selection_revision'] == 1
    before, active = current['item_bindings'][item_id]
    assert before['oem_evidence']['oem_number'] == 'FIXTURE-126480'
    assert active['oem_evidence']['oem_number'] == 'FIXTURE-126481'
    assert (active['source_modification_id'], active['product_id'], active['snapshot_sha']) == (126481, 106, '2'*64)
    assert active['supplier_articles'] == [{'supplier_id': 2, 'article_number': 'EXAMPLE'}]
    assert current['catalogue_oems']['106']['candidates'] == ['FIXTURE-126481']
    assert current['oems']['106']['oem_status'] == 'catalogue_applicable'
    assert logged.post(url+'/unified-catalogue/stock', json=stock).json() == {'added': 0, 'skipped': 1}

    path = f'/api/v1/parts/{part_id}/characteristics'
    number = current['oems']['106']['oem_number']
    response = logged.patch(path, json=dict(expected={'oem_number': number},
        values={'oem_number': number}, confirm_physical_oem=True))
    assert response.status_code == 200, response.text
    assert state()['oems']['106']['oem_status'] == 'physical_confirmed'
    response = logged.patch(path, json=dict(expected={'oem_number': number}, values={'oem_number': 'MANUAL'}))
    assert response.status_code == 200, response.text
    assert logged.post(url+'/catalogue-selection', json=selection(126480, current)).status_code == 200
    enrich()
    result = state()
    assert result['oems']['106']['oem_number'] == 'MANUAL'
    assert result['catalogue_oems']['106']['oem_number'] == 'FIXTURE-126480'
    assert len(result['item_bindings'][item_id]) == 3
    with Session(engine()) as db:
        operation = db.scalar(select(Operation).where(
            Operation.type == 'dismantling_receipt', Operation.entity_id == item_id))
        assert operation.after['catalogue_binding_at_receipt']['snapshot_sha'] == '1'*64
    assert physical_snapshot() == original


@pytest.mark.parametrize('failure', ['plan', 'articles', 'partial'])
def test_incomplete_catalogue_preserves_last_evidence(logged, catalogue_donor, failure):
    url, enrich, state, selection, failures, _ = catalogue_donor
    original = physical_snapshot()
    failures[126481] = failure
    response = logged.post(url+'/catalogue-selection', json=selection(126481, state()))
    if failure == 'plan':
        assert response.status_code == 503
        assert state()['selection_revision'] == 0
    else:
        assert response.status_code == 200
        enrich()
        result = state()
        assert result['catalogue_oems'] == {}
        assert result['oems']['106']['oem_number'] == 'FIXTURE-126480'
        assert result['oems']['106']['oem_status'] == 'historical'
        old, new = result['item_bindings'][original[1]]
        assert old['oem_evidence']['oem_number'] == 'FIXTURE-126480'
        assert 'supplier_articles' not in new
        del failures[126481]
        enrich()
        assert state()['catalogue_oems']['106']['oem_number'] == 'FIXTURE-126481'
    assert enrich('different-tenant') == 0
    assert physical_snapshot() == original


def test_concurrent_switch_rejects_stale_revision(logged, catalogue_donor):
    url, _, state, selection, _, _ = catalogue_donor
    current = state()
    requests = [selection(126481, current) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda request: logged.post(url+'/catalogue-selection', json=request), requests))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert state()['selection_revision'] == 1


def test_binding_history_and_selection_are_tenant_scoped(catalogue_donor):
    url, _, state, selection, _, _ = catalogue_donor
    current = state()
    with TestClient(app) as other:
        signup(other, 'another@example.test')
        assert other.get(url+'/global-dismantling').status_code == 404
        assert other.post(url+'/catalogue-selection', json=selection(126481, current)).status_code == 404
    assert state()['item_bindings'] == current['item_bindings']
