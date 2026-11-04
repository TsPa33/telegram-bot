"""Article receipt regression: no real Plan.Parts tokens or external requests."""
from sqlalchemy import text
from app.db import engine
from app.main import app
from app.api.plan_parts import plan_parts_client
from app.services.plan_parts import Article, PlanPartsError


def test_article_receipt_prevents_duplicate_paid_call_and_records_history(logged, vehicle):
    with engine().begin() as conn:
        conn.execute(text("UPDATE vehicles SET ktype=131094 WHERE id=:id"), {"id":vehicle["id"]})
    first_offer=Article(art_id=701, article_nr="PART-701", brand="Example Brand", part_name="Starter battery")
    state={"cached": False, "paid_calls":0}

    class Provider:
        def articles(self, account_id, ktype, pt_id):
            assert ktype == 131094 and pt_id == 607
            state["paid_calls"] += 1
            state["cached"] = True
            return [first_offer]

        def recover_articles(self, account_id, ktype, pt_id):
            if not state["cached"]:
                raise PlanPartsError(409,"Temporary cache expired")
            return [first_offer]

    app.dependency_overrides[plan_parts_client] = Provider
    path="/api/v1/plan-parts/articles/lookup?vehicle_id="+vehicle["id"]+"&ktype=131094&pt_id=607"
    recovery=path.replace("/articles/lookup", "/articles/recover")
    history="/api/v1/plan-parts/articles/history?vehicle_id="+vehicle["id"]+"&ktype=131094"
    try:
        initial=logged.post(path)
        assert initial.status_code==200,initial.text
        assert initial.json()["total"]==1
        assert initial.json()["from_cache"] is False
        assert state["paid_calls"]==1

        again=logged.post(path)
        assert again.status_code==200,again.text
        assert again.json()["from_cache"] is True
        assert state["paid_calls"]==1

        status=logged.get(history)
        assert status.status_code==200,status.text
        row=next(x for x in status.json()["receipts"] if x["pt_id"]==607)
        assert row["status"]=="received" and row["article_count"]==1 and row["received_at"]

        state["cached"]=False
        nocharge=logged.post(recovery)
        assert nocharge.status_code==200,nocharge.text
        assert nocharge.json()["from_saved"] is True
        assert nocharge.json()["articles"][0]["article_nr"]=="PART-701"
        assert state["paid_calls"]==1

        protected=logged.post(path)
        assert protected.status_code==200,protected.text
        assert protected.json()["from_saved"] is True
        assert protected.json()["articles"][0]["brand"]=="Example Brand"
        assert state["paid_calls"]==1

        saved=logged.get(history)
        receipt=next(x for x in saved.json()["receipts"] if x["pt_id"]==607)
        assert receipt["status"]=="received" and receipt["stored"] is True
    finally:
        app.dependency_overrides.pop(plan_parts_client,None)


def test_chosen_article_and_brand_persist_in_inventory_card(logged, vehicle):
    with engine().begin() as conn:
        conn.execute(text("UPDATE vehicles SET ktype=131094 WHERE id=:id"), {"id":vehicle["id"]})

    offer=Article(art_id=901,article_nr="BATT-901",brand="Example Supplier",part_name="Battery")
    class Provider:
        def recover_categories(self,account_id,ktype):
            from types import SimpleNamespace
            return [SimpleNamespace(pt_id=909)]
        def recover_articles(self,account_id,ktype,pt_id):
            return [offer]
    app.dependency_overrides[plan_parts_client]=Provider
    try:
        add=logged.post("/api/v1/plan-parts/donor-parts/add?vehicle_id="+vehicle["id"],
                        json={"ktype":131094,"pt_id":909,"ukrainian_name":"Акумулятор стартера"})
        assert add.status_code==200,add.text
        part_id=add.json()["part_id"]
        save=logged.post("/api/v1/plan-parts/donor-parts/article/select?vehicle_id="+vehicle["id"],
                         json={"ktype":131094,"pt_id":909,"art_id":901,"part_id":part_id})
        assert save.status_code==200,save.text
        assert save.json()["article_number"]=="BATT-901"
        assert save.json()["article_brand"]=="Example Supplier"
        status=logged.get("/api/v1/plan-parts/donor-parts/status?vehicle_id="+vehicle["id"]+"&ktype=131094")
        assert status.status_code==200,status.text
        part=next(x for x in status.json()["parts"] if x["id"]==part_id)
        assert part["article_number"]=="BATT-901" and part["article_brand"]=="Example Supplier"
        # Even after all in-memory supplier data disappears, assigning remains
        # possible from the validated PostgreSQL snapshot without another API call.
        class ExpiredProvider:
            def recover_articles(self, *args):
                raise AssertionError("Do not contact supplier cache after permanent snapshot")
        app.dependency_overrides[plan_parts_client]=ExpiredProvider
        same=logged.post("/api/v1/plan-parts/donor-parts/article/select?vehicle_id="+vehicle["id"],
                         json={"ktype":131094,"pt_id":909,"art_id":901,"part_id":part_id})
        assert same.status_code==200,same.text
        assert same.json()["changed"] is False
    finally:
        app.dependency_overrides.pop(plan_parts_client,None)
