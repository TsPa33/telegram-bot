"""Stage 10 integration: isolated test database and synthetic source snapshot only."""
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Vehicle, DismantlingItem, Part
from app.services import source_first_pilot
from app.services.auto_oem import enrich_vehicle


def source_snapshot(oem_types=40, equipment=False):
    categories = [
        dict(product_id=i, name_source=f"Original PRD {i}", kind="review",
             article_count=1, source_fitment_linked=True, category_path=[])
        for i in range(1, 51)
    ]
    if equipment:
        categories.append(dict(product_id=501, name_source="Equipment",
                               kind="equipment", article_count=1,
                               category_path=[]))
    return dict(schema="carpot.vehicle.plan.v1", manufacturer_id=120,
                car_id=107555, model_id=13084, modification=dict(
                    id=107555, description="T6 AWD"),
                coverage="partial", coverage_verified=False,
                taxonomy_status="unreviewed", observed_at="2026-11-23T06:00:00+00:00",
                source_snapshot_sha="a"*64, categories=categories)


class OfflineSnapshot:
    def __init__(self, payload, with_oem):
        self.payload = payload
        self.with_oem = with_oem

    def resolve_directory(self, vehicle):
        return (107555, 13084, 120, "a"*64, True)

    def plan(self, identity):
        assert identity[:3] == (107555,13084,120)
        return self.payload

    def get_offer_batch(self, payload, products):
        return {
            pid: [dict(supplier_id=1, article_nr=str(pid), brand="Test supplier",
                       oem_numbers=[f"OE-{pid}"] if pid <= self.with_oem else [],
                       oem_sources={}, vin_verified=False)]
            for pid in products
        }

    def get_offers(self, payload, product):
        raise AssertionError("All required source articles were supplied by batch")

    def enrich_oracle_offers(self, payload, data, priority=None):
        return data

    def sibling_candidates(self, payload, products):
        return {}


@pytest.fixture
def fresh_donor(logged, monkeypatch):
    monkeypatch.setattr(source_first_pilot, "is_staging", lambda: True)
    monkeypatch.setenv(source_first_pilot.ENABLED_VARIABLE, "true")
    response = logged.post('/api/v1/vehicles',json={
        "manufacturer":"Volvo", "model":"XC90 II", "year":2016,
        "engine_code":"B4204T27", "fuel_type":"petrol",
        "drive_type":"AWD",
    })
    assert response.status_code == 201, response.text
    vehicle_id = response.json()["id"]
    with Session(engine()) as db:
        return vehicle_id, db.get(Vehicle, vehicle_id).account_id


def test_staging_pilot_blocks_poor_source_without_inventory(fresh_donor):
    vehicle_id, account = fresh_donor
    cache = OfflineSnapshot(source_snapshot(), with_oem=20)
    assert enrich_vehicle(engine(), account, vehicle_id, cache) == 0
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(DismantlingItem)) == 0
        assert db.scalar(select(func.count()).select_from(Part)) == 0


def test_staging_pilot_accepts_exact_source_rows_and_excludes_equipment(fresh_donor):
    vehicle_id, account = fresh_donor
    cache = OfflineSnapshot(source_snapshot(equipment=True), with_oem=40)
    assert enrich_vehicle(engine(), account, vehicle_id, cache) >= 1
    with Session(engine()) as db:
        rows = list(db.scalars(select(DismantlingItem)))
        assert len(rows) == 50
        assert all(r.source=="carpot.catalogue.v1" for r in rows)
        assert all(r.catalog_key.startswith("car:107555:product:") for r in rows)
        assert all("product:501" not in r.catalog_key for r in rows)
        assert db.scalar(select(func.count()).select_from(Part)) == 0
        vehicle = db.get(Vehicle, vehicle_id)
        assert vehicle.dismantling_v3["unified_catalogue"]["payload"]["car_id"] == 107555
        refs = vehicle.dismantling_v3.get("volvo_oem_references",{})
        assert len(refs) == 40
        assert all(r.get("vin_verified") is False for r in refs.values())

def test_pilot_off_keeps_stage2_legacy_behavior_for_unreviewed_types(fresh_donor, monkeypatch):
    # Opt-in must never silently create a new donor plan when disabled.
    vehicle_id, account = fresh_donor
    monkeypatch.setenv(source_first_pilot.ENABLED_VARIABLE, "false")
    payload = source_snapshot()
    for product in payload["categories"]:
        product["source_fitment_linked"] = False
    assert enrich_vehicle(engine(), account, vehicle_id,
                          OfflineSnapshot(payload, with_oem=40)) == 0
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(DismantlingItem)) == 0
        assert db.scalar(select(func.count()).select_from(Part)) == 0


def test_stage10_uses_stage2_single_writer_and_keeps_source_sha(fresh_donor, monkeypatch):
    from app.services import unified_catalogue as catalogue
    vehicle_id, account = fresh_donor
    original_writer = catalogue.persist
    writes = []

    def observed_writer(db, vehicle, envelope, **kwargs):
        writes.append((envelope["payload"], kwargs))
        return original_writer(db, vehicle, envelope, **kwargs)

    monkeypatch.setattr(catalogue, "persist", observed_writer)
    assert enrich_vehicle(engine(), account, vehicle_id,
                          OfflineSnapshot(source_snapshot(equipment=True),
                                          with_oem=40)) >= 1
    assert len(writes) == 1
    written, options = writes[0]
    assert options == {"allow_partial": True}
    assert written["source_snapshot_sha"] == "a" * 64
    assert len(written["categories"]) == 50
    assert all(p["kind"] != "equipment" for p in written["categories"])
    with Session(engine()) as db:
        vehicle = db.get(Vehicle, vehicle_id)
        state = vehicle.dismantling_v3
        assert state["unified_catalogue"]["payload"]["source_snapshot_sha"] == "a" * 64
        bindings = state["catalogue_item_bindings"]
        assert len(bindings) == 50
        assert all(history[-1]["snapshot_sha"] == "a" * 64
                   and history[-1]["source_modification_id"] == 107555
                   for history in bindings.values())
