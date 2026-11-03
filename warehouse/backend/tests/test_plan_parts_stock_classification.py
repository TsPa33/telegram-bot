"""Plan.Parts type -> CarPot existing category; no provider costs, stock safe."""
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.api.plan_parts import plan_parts_client
from app.models import Category, Part
from app.services.plan_parts_classification import classify, match_existing_category


def test_universal_classifier_favors_explicit_subsystem_and_service_goods():
    assert classify("Accessory Kit, brake caliper")["section"] == "Гальмівна система"
    assert classify("Accessory Kit, brake caliper")["kind"] == "kit"
    assert classify("Bulb, auxiliary stop light")["section"] == "Освітлення"
    assert classify("Adjustment Tool Set, valve timing")["kind"] == "tool"
    assert classify("Adjustment Tool Set, valve timing")["section"] == "Обладнання та витратні матеріали"
    assert classify("Brake Service Paste")["kind"] == "consumable"
    assert classify("Brake Service Paste")["section"] == "Обладнання та витратні матеріали"
    assert classify("Auxiliary Water Pump (cooling water circuit)")["section"] == "Двигун та його системи"
    assert classify("Completely unknown part name")["section"] is None


def test_ambiguous_or_missing_categories_never_become_fake_ids(logged):
    account_id = next(iter(engine().connect().execute(text("SELECT id FROM accounts"))))[0]
    with Session(engine()) as db:
        suggestion = match_existing_category(db, account_id, classify("Brake Caliper"), "Гальмівний супорт")
        assert suggestion["category_id"] is None
        assert suggestion["mapping"] == "category_missing"


def test_stock_receipt_and_owner_confirmed_metadata_backfill(logged, vehicle):
    with engine().begin() as conn:
        account_id = conn.execute(text("SELECT id FROM accounts LIMIT 1")).scalar_one()
        conn.execute(text("UPDATE vehicles SET ktype=131094 WHERE id=:id"), {"id":vehicle["id"]})
    with Session(engine()) as db:
        brakes = Category(account_id=account_id, source="test", external_key="brakes",
                          name="Гальмівна система", kind="category")
        db.add(brakes)
        db.commit()
        category_id = brakes.id

    class CacheOnly:
        def recover_categories(self, account_id, ktype):
            return [SimpleNamespace(pt_id=800, name="Brake Caliper")]
    app.dependency_overrides[plan_parts_client] = lambda: CacheOnly()
    try:
        endpoint="/api/v1/plan-parts/donor-parts/add?vehicle_id="+vehicle["id"]
        first=logged.post(endpoint,json={"ktype":131094,"pt_id":800,"ukrainian_name":"Гальмівний супорт"})
        assert first.status_code == 200, first.text
        part_id=first.json()["part_id"]
        with Session(engine()) as db:
            part=db.get(Part,part_id)
            assert part.category_id == category_id
            assert part.quantity == 1
            assert part.subcategory_id is None
            # Emulate a historical uncategorized part, without changing stock.
            part.category_id = None
            db.commit()

        preview=logged.get("/api/v1/plan-parts/donor-parts/classification/preview?vehicle_id="+vehicle["id"]+"&ktype=131094")
        assert preview.status_code==200, preview.text
        assert preview.json()["can_apply"]==1
        assert preview.json()["rows"][0]["section"]=="Гальмівна система"
        apply=logged.post("/api/v1/plan-parts/donor-parts/classification/apply?vehicle_id="+vehicle["id"]+"&ktype=131094")
        assert apply.status_code==200, apply.text
        assert apply.json()["updated_count"]==1
        repeated=logged.post("/api/v1/plan-parts/donor-parts/classification/apply?vehicle_id="+vehicle["id"]+"&ktype=131094")
        assert repeated.status_code==200,repeated.text
        assert repeated.json()["updated_count"]==0

        with Session(engine()) as db:
            updated=db.get(Part,part_id)
            assert updated.category_id==category_id
            assert updated.quantity==1
            assert updated.selling_price is None
            assert updated.physical_location_kind=="on_vehicle"
    finally:
        app.dependency_overrides.pop(plan_parts_client,None)
