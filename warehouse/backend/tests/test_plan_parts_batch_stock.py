"""A bulk stock request uses the existing audited/idempotent receipt route."""
from types import SimpleNamespace

from sqlalchemy import text

from app.api.plan_parts import plan_parts_client
from app.db import engine
from app.main import app


def test_selected_batch_receives_without_selling_supplier_tokens(logged, vehicle):
    with engine().begin() as conn:
        conn.execute(text("UPDATE vehicles SET ktype=131094 WHERE id=:id"),
                     {"id": vehicle["id"]})

    class CacheOnlyCatalogue:
        def recover_categories(self, account_id, ktype):
            assert ktype == 131094
            return [
                SimpleNamespace(pt_id=90001, name="Brake Caliper"),
                SimpleNamespace(pt_id=90002, name="Bulb, auxiliary stop light"),
            ]

    app.dependency_overrides[plan_parts_client] = lambda: CacheOnlyCatalogue()
    endpoint = "/api/v1/plan-parts/donor-parts/add-batch?vehicle_id="+vehicle["id"]
    payload = {"items": [
        {"ktype":131094,"pt_id":90001,"ukrainian_name":"Гальмівний супорт"},
        {"ktype":131094,"pt_id":90002,"ukrainian_name":"Лампа додаткового стоп-сигналу"},
    ]}
    try:
        result = logged.post(endpoint, json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["completed"] == 2
        assert all(r["quantity"] == 1 for r in result.json()["results"])
        repeat = logged.post(endpoint, json=payload)
        assert repeat.status_code == 200, repeat.text
        assert repeat.json()["completed"] == 2
        assert all(r["received"] is False for r in repeat.json()["results"])
        status = logged.get("/api/v1/vehicles/" + vehicle["id"])
        assert status.status_code == 200
        assert status.json()["stock_positions"] == 2
        dupe = logged.post(endpoint, json={"items":[payload["items"][0],payload["items"][0]]})
        assert dupe.status_code == 422
    finally:
        app.dependency_overrides.pop(plan_parts_client,None)
