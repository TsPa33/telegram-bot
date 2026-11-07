"""Focused disposable PostgreSQL coverage; every provider operation is offline."""

import ast, json, subprocess, time
import pytest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func, event
from sqlalchemy.orm import Session
from app.db import engine
from app.models import (
    Vehicle,
    Part,
    VehicleChecklistItem,
    Category,
    SourceTypeMapping,
    Operation,
    Account,
)
from app.api.deps import Identity
from app.api import plan_parts as api
from app.services import donor_stock_batch
from test_approved_dismantling import setup, read
from test_v3_release_audit import all_tables


def seed(v, n=100, start=1000):
    with Session(engine()) as db:
        donor = db.get(Vehicle, v["id"])
        for i in range(n):
            db.add(
                VehicleChecklistItem(
                    account_id=donor.account_id,
                    vehicle_id=donor.id,
                    source="plan.parts",
                    ktype=123,
                    pt_id=start + i,
                    name_en=f"Starter component {i}",
                    name_uk=f"Стартер {i}",
                    article_count=0,
                )
            )
        db.commit()
    return [
        {"ktype": 123, "pt_id": start + i, "ukrainian_name": f"Стартер {i}"}
        for i in range(n)
    ]


def provision(c, v):
    path = "/api/v1/plan-parts/donor-parts/classification/"
    r = c.get(
        path + "preview",
        params={"vehicle_id": v["id"], "ktype": 123, "provision": True},
    )
    assert r.status_code == 200, r.text
    result = c.post(
        path + "apply",
        params={"vehicle_id": v["id"], "ktype": 123},
        json={"token": r.json()["token"], "provision": True},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_category_preview_apply_history_manual_protection(setup):
    c, v = setup
    r = c.post(
        "/api/v1/plan-parts/donor-parts/add-batch",
        params={"vehicle_id": v["id"]},
        json={
            "items": [
                {"ktype": 123, "pt_id": i, "ukrainian_name": n}
                for i, n in [(1, "Стартер"), (3, "Гальмівний супорт")]
            ]
        },
    )
    assert r.status_code == 200, r.text
    with Session(engine()) as db:
        before = all_tables(db)
    p = c.get(
        "/api/v1/plan-parts/donor-parts/classification/preview",
        params={"vehicle_id": v["id"], "ktype": 123, "provision": True},
    )
    assert p.status_code == 200, p.text
    preview_token = p.json()["token"]
    with Session(engine()) as db:
        assert all_tables(db) == before
    result = provision(c, v)
    assert result["counts"]["matched"] == 2
    with Session(engine()) as db:
        ps = list(db.scalars(select(Part).where(Part.vehicle_id == v["id"])))
        assert all(p.category_id and p.quantity == 1 for p in ps)
        assert db.scalar(select(func.count()).select_from(SourceTypeMapping)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(Category)
                .where(Category.kind == "category", Category.parent_id.is_(None))
            )
            == 12
        )
        original = {
            p.id: (
                p.quantity,
                p.reserved_quantity,
                p.selling_price,
                p.article_number,
                p.oem_number,
            )
            for p in ps
        }
        # User assignment wins even if it disagrees with automatic supplier mapping.
        ps[0].category_id = db.scalar(
            select(Category.id).where(
                Category.kind == "category", Category.name == "Освітлення"
            )
        )
        ps[0].subcategory_id = None
        manual = (ps[0].id, ps[0].category_id)
        db.commit()
    again = provision(c, v)
    assert again["counts"]["protected"] == 2
    with Session(engine()) as db:
        assert db.get(Part, manual[0]).category_id == manual[1]
        for id, values in original.items():
            p = db.get(Part, id)
            assert (
                p.quantity,
                p.reserved_quantity,
                p.selling_price,
                p.article_number,
                p.oem_number,
            ) == values
    assert (
        c.post(
            "/api/v1/plan-parts/donor-parts/classification/apply",
            params={"vehicle_id": v["id"], "ktype": 123},
            json={"token": preview_token, "provision": True},
        ).status_code
        == 409
    )


def test_batch_atomic_identity_replay_zero_and_original_search(setup, monkeypatch):
    c, v = setup
    provision(c, v)
    items = seed(v, 2)
    items[0]["ukrainian_name"] = items[1]["ukrainian_name"] = "Однакова назва"
    path = "/api/v1/plan-parts/donor-parts/add-batch?vehicle_id=" + v["id"]
    from fastapi.testclient import TestClient
    from app.main import app
    from conftest import signup

    with TestClient(app) as other:
        signup(other, "other-batch@example.test")
        assert other.post(path, json={"items": items}).status_code == 404
        assert (
            other.get(
                "/api/v1/plan-parts/donor-parts/classification/preview",
                params={"vehicle_id": v["id"], "ktype": 123},
            ).status_code
            == 404
        )
    assert (
        c.post(path, json={"items": items}, headers={"X-CSRF-Token": ""}).status_code
        == 403
    )
    before = None
    with Session(engine()) as db:
        before = all_tables(db)
    assert (
        c.post(
            path,
            json={
                "items": items
                + [{"ktype": 123, "pt_id": 99999, "ukrainian_name": "Невідома"}]
            },
        ).status_code
        == 422
    )
    with Session(engine()) as db:
        assert all_tables(db) == before
    r = c.post(path, json={"items": items})
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 2
    ids = [x["part_id"] for x in r.json()["results"]]
    assert len(set(ids)) == 2
    # Failure after ORM inserts must roll back stock and operations as one unit.
    more = seed(v, 2, 2000)
    original_stock = donor_stock_batch.stock

    def fail(*a, **kw):
        raise RuntimeError("forced test rollback")

    monkeypatch.setattr(donor_stock_batch, "stock", fail)
    with pytest.raises(RuntimeError, match="forced test rollback"):
        c.post(path, json={"items": more})
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Part).where(Part.vehicle_id == v["id"])
            )
            == 2
        )
    monkeypatch.setattr(donor_stock_batch, "stock", original_stock)
    # Zero stock is not permission to receive the same original component twice.
    part = c.get("/api/v1/parts/" + ids[0]).json()
    assert (
        c.post(
            "/api/v1/parts/" + ids[0] + "/operations",
            json={
                "type": "write_off",
                "quantity": 1,
                "reason": "Локальний тест списання",
            },
        ).status_code
        == 200
    )
    replay = c.post(path, json={"items": items})
    assert replay.status_code == 200, replay.text
    assert replay.json()["added"] == 0 and replay.json()["skipped"] == 2
    assert c.get("/api/v1/parts/" + ids[0]).json()["quantity"] == 0
    search = c.get("/api/v1/parts", params={"q": "Starter component 1"}).json()
    assert any(p["id"] == ids[1] for p in search["items"])


def test_batch_concurrency_and_reserved_stock(setup):
    c, v = setup
    items = seed(v, 10)
    path = "/api/v1/plan-parts/donor-parts/add-batch?vehicle_id=" + v["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: c.post(path, json={"items": items}), range(2))
        )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert sum(r.json()["added"] for r in results) == 10
    id = results[0].json()["results"][0]["part_id"]
    assert (
        c.post(
            "/api/v1/parts/" + id + "/operations",
            json={"type": "reserve", "quantity": 1, "reason": "Локальний тест резерву"},
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/api/v1/parts/" + id + "/operations",
            json={"type": "write_off", "quantity": 1, "reason": "Захист резерву"},
        ).status_code
        == 409
    )
    assert (
        c.post(
            "/api/v1/parts/" + id + "/operations",
            json={"type": "correction", "quantity": 0, "reason": "Захист резерву"},
        ).status_code
        == 409
    )
    p = c.get("/api/v1/parts/" + id).json()
    assert p["quantity"] == 1 and p["reserved_quantity"] == 1


def test_batch_100_profile_against_previous_implementation(setup):
    c, v = setup
    items = seed(v, 100)
    old_source = subprocess.check_output(
        [
            "git",
            "show",
            "993c5224d84e5522874e0b655134f286a41f6ac0:warehouse/backend/app/api/plan_parts.py",
        ],
        text=True,
    )
    tree = ast.parse(old_source)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "add_selected_donor_part"
    )
    fn.decorator_list = []
    fn.name = "legacy_add"
    namespace = dict(api.__dict__)
    exec(
        compile(
            ast.Module(body=[fn], type_ignores=[]),
            "<previous-reviewed-implementation>",
            "exec",
        ),
        namespace,
    )
    stats = {
        "legacy": {"queries": 0, "commits": 0},
        "batch": {"queries": 0, "commits": 0},
    }
    phase = ["legacy"]

    def query(*a):
        if phase[0] in stats:
            stats[phase[0]]["queries"] += 1

    def commit(*a):
        if phase[0] in stats:
            stats[phase[0]]["commits"] += 1

    event.listen(engine(), "before_cursor_execute", query)
    event.listen(Session, "after_commit", commit)
    try:
        with Session(engine()) as db:
            donor = db.get(Vehicle, v["id"])
            owner = db.get(Account, donor.account_id)
            who = Identity(owner, None, owner.id, owner.id, frozenset())
            start = time.perf_counter()
            for item in items:
                namespace["legacy_add"](
                    api.AddSelectedDonorPart(**item), who, None, db, v["id"]
                )
            stats["legacy"]["seconds"] = round(time.perf_counter() - start, 4)
        phase[0] = "setup"
        # Another donor with identical saved type IDs; no copied inventory.
        new = c.post(
            "/api/v1/vehicles",
            json={"manufacturer": "TEST", "model": "BATCH", "year": 2009},
        ).json()
        with Session(engine()) as db:
            db.get(Vehicle, new["id"]).ktype = 123
            db.commit()
        seed(new, 100)
        phase[0] = "batch"
        start = time.perf_counter()
        r = c.post(
            "/api/v1/plan-parts/donor-parts/add-batch?vehicle_id=" + new["id"],
            json={"items": items},
        )
        stats["batch"]["seconds"] = round(time.perf_counter() - start, 4)
        assert r.status_code == 200, r.text
        assert r.json()["added"] == 100
        assert stats["batch"]["commits"] == 1
        assert stats["batch"]["queries"] < 40, stats
    finally:
        event.remove(engine(), "before_cursor_execute", query)
        event.remove(Session, "after_commit", commit)
    print("PROFILE_100=" + json.dumps(stats))
    open("/tmp/carpot-stabilization-profile.json", "w").write(
        json.dumps(stats, indent=2)
    )


def test_same_type_after_modification_change_preserves_stock_manual_name_and_exclusion(
    setup,
):
    c, v = setup
    base = "/api/v1/plan-parts/"
    first = c.post(
        base + "donor-parts/add",
        params={"vehicle_id": v["id"]},
        json={"ktype": 123, "pt_id": 1, "ukrainian_name": "Стартер"},
    ).json()
    annotation = "/api/v1/vehicles/" + v["id"] + "/dismantling-workspace/annotations"
    assert (
        c.post(
            annotation,
            json={
                "source": "professional",
                "keys": ["pp:123:1"],
                "action": "rename",
                "name": "Виправлений стартер",
            },
        ).status_code
        == 200
    )
    assert (
        c.post(
            annotation,
            json={"source": "professional", "keys": ["pp:123:1"], "action": "hide"},
        ).status_code
        == 200
    )
    assert (
        c.post(
            base + "vehicle-modification/select",
            params={"vehicle_id": v["id"]},
            json={"ktype": 456, "confirm_change": True},
        ).status_code
        == 200
    )
    with Session(engine()) as db:
        donor = db.get(Vehicle, v["id"])
        db.add(
            VehicleChecklistItem(
                account_id=donor.account_id,
                vehicle_id=donor.id,
                source="plan.parts",
                ktype=456,
                pt_id=1,
                name_en="Starter",
                name_uk="",
                article_count=3,
            )
        )
        db.commit()
    r = c.post(
        base + "donor-parts/add-batch",
        params={"vehicle_id": v["id"]},
        json={
            "items": [{"ktype": 456, "pt_id": 1, "ukrainian_name": "Інший переклад"}]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 0 and r.json()["review_required"] == 1
    row = read(c, v)["items"][0]
    assert row["parts"][0]["id"] == first["part_id"] and row["context_matches"] is False
    assert row["name"] == "Виправлений стартер" and row["state"] == "hidden"
    assert (
        c.post(
            annotation,
            json={"source": "professional", "keys": ["pp:456:1"], "action": "restore"},
        ).status_code
        == 200
    )
    row = read(c, v)["items"][0]
    assert row["name"] == "Виправлений стартер" and row["state"] != "hidden"
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Part).where(Part.vehicle_id == v["id"])
            )
            == 1
        )
        part = db.get(Part, first["part_id"])
        assert (
            part.quantity == 1
            and part.compatibility_notes == "plan.parts:ktype=123;pt_id=1"
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Operation)
                .where(Operation.part_id == part.id, Operation.type == "receipt")
            )
            == 1
        )
