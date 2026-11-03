"""One-click plan.parts stock receipt: idempotent, auditable, no paid supplier calls."""
from types import SimpleNamespace
from sqlalchemy import text
from app.db import engine
from app.main import app
from app.api.plan_parts import plan_parts_client


def test_selected_part_creates_one_stock_unit_and_does_not_duplicate(logged, vehicle):
    with engine().begin() as conn:
        conn.execute(text("UPDATE vehicles SET ktype=:ktype WHERE id=:id"),
                     {"ktype":131094, "id":vehicle["id"]})

    class CacheOnlyCatalogue:
        def recover_categories(self, account_id, ktype):
            assert ktype==131094
            return [SimpleNamespace(pt_id=555), SimpleNamespace(pt_id=556)]

    app.dependency_overrides[plan_parts_client]=lambda:CacheOnlyCatalogue()
    payload={"ktype":131094,"pt_id":555,"ukrainian_name":"Гальмівний супорт"}
    url="/api/v1/plan-parts/donor-parts/add?vehicle_id="+vehicle["id"]
    try:
        first=logged.post(url,json=payload)
        assert first.status_code==200,first.text
        assert first.json()["created"] is True
        assert first.json()["received"] is True
        assert first.json()["quantity"]==1
        repeated=logged.post(url,json=payload)
        assert repeated.status_code==200,repeated.text
        assert repeated.json()["created"] is False
        assert repeated.json()["received"] is False
        assert repeated.json()["quantity"]==1
        donor=logged.get("/api/v1/vehicles/"+vehicle["id"])
        assert donor.status_code==200,donor.text
        assert donor.json()["stock_positions"]==1
        assert donor.json()["registered_parts"]==1
        status=logged.get("/api/v1/plan-parts/donor-parts/status?vehicle_id="+vehicle["id"]+"&ktype=131094")
        assert status.status_code==200,status.text
        assert len(status.json()["parts"])==1
        assert status.json()["parts"][0]["pt_id"]==555
        assert status.json()["parts"][0]["quantity"]==1

        # Two different supplier pt_ids can translate to the same physical
        # donor-part name. Do not create another stock unit for same donor.
        same_title=logged.post(url,json={**payload,"pt_id":556,"ukrainian_name":"  ГАЛЬМІВНИЙ   СУПОРТ  "})
        assert same_title.status_code==200,same_title.text
        assert same_title.json()["part_id"]==first.json()["part_id"]
        assert same_title.json()["created"] is False
        assert same_title.json()["received"] is False
        assert same_title.json()["quantity"]==1
        status_after=logged.get("/api/v1/plan-parts/donor-parts/status?vehicle_id="+vehicle["id"]+"&ktype=131094")
        assert len(status_after.json()["parts"])==1


        with engine().begin() as conn:
            events=conn.execute(text(
                "SELECT type FROM operations WHERE part_id=:id ORDER BY created_at"
            ),{"id":first.json()["part_id"]}).scalars().all()
        assert events.count("receipt")==1

        # Older UI created the same part at zero quantity. Re-admission to
        # inventory is audited once; it must never create a second Part row.
        reset=logged.post(
            "/api/v1/parts/"+first.json()["part_id"]+"/operations",
            json={"type":"correction","quantity":0,"reason":"Test correction of inventory"},
        )
        assert reset.status_code==200,reset.text
        recovered=logged.post(url,json=payload)
        assert recovered.status_code==200,recovered.text
        assert recovered.json()["created"] is False
        assert recovered.json()["received"] is True
        assert recovered.json()["quantity"]==1
        reset_again=logged.post(
            "/api/v1/parts/"+first.json()["part_id"]+"/operations",
            json={"type":"correction","quantity":0,"reason":"Test historical zero quantity"},
        )
        assert reset_again.status_code==200,reset_again.text
        migrate=logged.post(
            "/api/v1/plan-parts/donor-parts/receive-pending?vehicle_id="+vehicle["id"]+"&ktype=131094",
        )
        assert migrate.status_code==200,migrate.text
        assert migrate.json()["received_count"]==1
        migrate_again=logged.post(
            "/api/v1/plan-parts/donor-parts/receive-pending?vehicle_id="+vehicle["id"]+"&ktype=131094",
        )
        assert migrate_again.status_code==200,migrate_again.text
        assert migrate_again.json()["received_count"]==0
    finally:
        app.dependency_overrides.pop(plan_parts_client,None)
