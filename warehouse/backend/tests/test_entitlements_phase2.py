from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Account, Vehicle, Part, Operation, now
from app.models.entitlements import EntitlementWorkspace
from app.services import entitlements as e

KEY = "phase2-local-fixture-key-not-a-real-credential-12345"


def interval(plan="standard", kind="base", start=None, end=None, capacity=None):
    return dict(
        plan=plan,
        kind=kind,
        effective_from=(start or now() - timedelta(days=1)).isoformat(),
        effective_until=(end or now() + timedelta(days=29)).isoformat(),
        vehicle_capacity=capacity
        if capacity is not None
        else e.PLANS[plan]["vehicle_capacity"],
        employee_seats=0 if kind == "addon" else e.PLANS[plan]["employee_seats"],
    )


@pytest.fixture
def pilot(logged, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENTITLEMENTS_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_ENTITLEMENT_TEST_KEY", KEY)
    w = logged.get("/api/v1/auth/me").json()["id"]
    r = logged.post("/api/v1/billing/bind")
    assert r.status_code == 200, r.text

    def project(intervals, mode="enforce", version=None):
        with Session(engine()) as db:
            p = db.get(EntitlementWorkspace, w)
            payload = dict(
                schema_version=2,
                event_id=str(uuid4()),
                environment="test",
                workspace_id=w,
                billing_account_id=p.billing_account_id,
                version=version or p.version + 1,
                intervals=intervals,
                trial_used=False,
            )
            e.accept(
                db, e.local_bridge().publish_fixture(w, p.billing_account_id, intervals)
            )
            p = db.get(EntitlementWorkspace, w)
            p.mode = mode
            db.commit()
        return payload

    project([interval()])
    return logged, w, project


def vehicle(i):
    return dict(manufacturer="Test", model="Donor", year=2020, donor_id="D-" + str(i))


@pytest.mark.parametrize("plan,limit", [("standard", 10), ("premium", 50)])
def test_first_last_and_over_capacity(pilot, plan, limit):
    c, w, project = pilot
    project([interval(plan)])
    for i in range(limit):
        r = c.post("/api/v1/vehicles", json=vehicle(i))
        assert r.status_code == 201, r.text
    assert c.post("/api/v1/vehicles", json=vehicle(limit)).status_code == 409
    assert c.get("/api/v1/billing/entitlements").json()["usage"]["vehicles"] == limit
    project([interval(plan)])
    assert c.post("/api/v1/vehicles", json=vehicle(limit + 1)).status_code == 409


def test_last_place_concurrency_and_restore(pilot):
    c, w, _ = pilot
    for i in range(9):
        assert c.post("/api/v1/vehicles", json=vehicle(i)).status_code == 201

    def add(n):
        with Session(engine()) as db:
            db.add(Vehicle(account_id=w, number=n, **vehicle(n)))
            try:
                db.commit()
                return 201
            except HTTPException as ex:
                db.rollback()
                return ex.status_code

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(add, [100, 101])) == [201, 409]
    item = c.get("/api/v1/vehicles").json()["items"][0]
    assert c.post("/api/v1/archive/vehicles/" + item["id"]).status_code == 200
    assert c.post("/api/v1/vehicles", json=vehicle(200)).status_code == 201
    assert (
        c.post("/api/v1/archive/vehicles/" + item["id"] + "?restore=true").status_code
        == 409
    )


def test_archive_hidden_parts_provenance_and_return(pilot):
    c, w, project = pilot
    v = c.post("/api/v1/vehicles", json=vehicle(1)).json()
    p = c.post("/api/v1/parts", json={"name": "Physical", "vehicle_id": v["id"]}).json()

    def stock(kind):
        return c.post(
            "/api/v1/parts/" + p["id"] + "/operations",
            json={"type": kind, "quantity": 1, "reason": "fixture operation"},
        )

    assert stock("receipt").status_code == 200
    assert c.post("/api/v1/archive/vehicles/" + v["id"]).status_code == 409
    assert c.post("/api/v1/archive/parts/" + p["id"]).status_code == 200
    assert c.post("/api/v1/archive/vehicles/" + v["id"]).status_code == 409
    with Session(engine()) as db:
        row = db.get(Part, p["id"])
        row.assortment_enabled = False
        db.commit()
        row.vehicle_id = None
        with pytest.raises(HTTPException):
            db.commit()
        db.rollback()
        assert e.usage(db, w)["vehicles"] == 1
        row = db.get(Part, p["id"])
        row.assortment_enabled = True
        row.archived = False
        db.commit()
    assert stock("reserve").status_code == 200
    assert c.post("/api/v1/archive/vehicles/" + v["id"]).status_code == 409
    assert stock("release").status_code == 200
    assert stock("sale").status_code == 200
    assert c.post("/api/v1/archive/vehicles/" + v["id"]).status_code == 200
    with Session(engine()) as db:
        sale = db.scalar(
            select(Operation).where(
                Operation.part_id == p["id"], Operation.type == "sale"
            )
        ).id
    project([interval(start=now() - timedelta(days=34), end=now() - timedelta(days=4))])
    data = dict(sale_id=sale, quantity=1, request_key=str(uuid4()))
    r = c.post("/api/v1/billing/returns", json=data)
    assert r.status_code == 200, r.text
    assert c.post("/api/v1/billing/returns", json=data).json()["replayed"]
    assert (
        c.post(
            "/api/v1/billing/returns", json={**data, "request_key": str(uuid4())}
        ).status_code
        == 409
    )
    with Session(engine()) as db:
        assert db.get(Part, p["id"]).quantity == 1 and e.usage(db, w)["vehicles"] == 1


def test_free_grace_expiry_and_default_off(pilot, monkeypatch):
    c, w, project = pilot
    project([])
    assert c.get("/api/v1/vehicles").status_code == 200
    assert c.post("/api/v1/vehicles", json=vehicle(1)).status_code == 402
    assert c.post("/api/v1/parts", json={"name": "Blocked"}).status_code == 402
    project([interval(start=now() - timedelta(days=31), end=now() - timedelta(days=1))])
    assert c.get("/api/v1/billing/entitlements").json()["status"] == "GRACE"
    assert c.post("/api/v1/vehicles", json=vehicle(2)).status_code == 201
    project([interval(start=now() - timedelta(days=34), end=now() - timedelta(days=4))])
    assert c.post("/api/v1/vehicles", json=vehicle(3)).status_code == 402
    assert c.get("/api/v1/vehicles").json()["total"] == 1
    monkeypatch.delenv("WAREHOUSE_ENTITLEMENTS_ENABLED")
    assert c.post("/api/v1/vehicles", json=vehicle(4)).status_code == 201


def test_downgrade_addon_expiry_time_windows(pilot):
    c, w, project = pilot
    start = now() - timedelta(days=1)
    boundary = now() + timedelta(days=2)
    project(
        [
            interval("premium", start=start, end=boundary),
            interval("standard", start=boundary, end=boundary + timedelta(days=30)),
            interval(
                kind="addon", start=start, end=now() + timedelta(hours=1), capacity=5
            ),
        ]
    )
    with Session(engine()) as db:
        assert e.state(db, w)["vehicle_capacity"] == 55
        assert e.state(db, w, at=now() + timedelta(hours=2))["vehicle_capacity"] == 50
        assert (
            e.state(db, w, at=boundary + timedelta(hours=1))["vehicle_capacity"] == 10
        )
    for i in range(11):
        assert c.post("/api/v1/vehicles", json=vehicle(i)).status_code == 201
    project([interval("standard")])
    assert c.get("/api/v1/billing/entitlements").json()["over_limit"]["vehicles"]
    assert c.post("/api/v1/vehicles", json=vehicle(99)).status_code == 409
    assert c.get("/api/v1/vehicles").json()["total"] == 11


def test_trial_atomic_deadline_and_expiry(pilot):
    c, w, project = pilot
    project([])
    r = c.post("/api/v1/billing/trial", json={"plan": "standard"})
    assert r.status_code == 200, r.text
    deadline = r.json()["period_end"]
    assert c.post("/api/v1/billing/trial", json={"plan": "standard"}).status_code == 409
    r = c.post("/api/v1/billing/trial", json={"plan": "premium"})
    assert r.status_code == 200, r.text
    assert r.json()["period_end"] == deadline
    with Session(engine()) as db:
        p = db.get(EntitlementWorkspace, w)
        end = datetime.fromisoformat(p.intervals[0]["effective_until"])
        assert e.state(db, w, at=end + timedelta(seconds=1))["status"] == "EXPIRED"
    assert (
        c.post(
            "/api/v1/billing/trial",
            json={"plan": "standard", "workspace_id": "foreign"},
        ).status_code
        == 422
    )


def test_team_concurrency_and_reactivation(pilot):
    c, w, _ = pilot

    def add(n):
        with Session(engine()) as db:
            db.add(
                Account(
                    name="Worker",
                    email=f"{uuid4()}@example.test",
                    password_hash="fixture",
                    workspace_account_id=w,
                    role="MANAGER",
                    permissions=[],
                )
            )
            try:
                db.commit()
                return 201
            except HTTPException as ex:
                db.rollback()
                return ex.status_code

    for i in range(4):
        assert add(i) == 201
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(add, [5, 6])) == [201, 409]
    with Session(engine()) as db:
        worker = db.scalar(select(Account).where(Account.workspace_account_id == w))
        worker.is_active = False
        worker_id = worker.id
        db.commit()
    assert add(7) == 201
    with Session(engine()) as db:
        worker = db.get(Account, worker_id)
        worker.is_active = True
        with pytest.raises(HTTPException):
            db.commit()


def test_transport_scope_binding_and_replay(pilot):
    c, w, project = pilot
    from bot.billing.models import BillingError

    bridge = e.local_bridge()
    with Session(engine()) as db:
        p = db.get(EntitlementWorkspace, w)
        data = dict(
            schema_version=2,
            event_id=str(uuid4()),
            environment="test",
            workspace_id=w,
            billing_account_id=p.billing_account_id,
            version=p.version + 1,
            intervals=[interval()],
            trial_used=False,
        )
        token = bridge.entitlement_transport.sign(data)
        assert e.accept(db, token) == "applied"
        db.commit()
        with pytest.raises(HTTPException):
            e.accept(db, token)
        db.rollback()
        with pytest.raises(BillingError):
            bridge.owner_transport.verify(token)
        with pytest.raises(BillingError):
            bridge.entitlement_transport.verify(token + "bad")
        with pytest.raises(BillingError):
            bridge.entitlement_transport.verify(
                bridge.entitlement_transport.sign(data, now=1)
            )
        with pytest.raises(HTTPException):
            e.accept(
                db,
                bridge.entitlement_transport.sign(
                    {**data, "billing_account_id": "foreign"}
                ),
            )
    assert (
        c.post(
            "/api/v1/billing/quote", json={"pack": "pack_1", "workspace_id": "foreign"}
        ).status_code
        == 422
    )


def test_old_order_completion_cannot_add_quantity_after_expiry(pilot):
    c, w, project = pilot
    from test_orders import buyer, stocked, line, create, action

    v = c.post("/api/v1/vehicles", json=vehicle(5)).json()
    b = buyer(c)
    p = stocked(c, v, quantity=3)
    order = create(c, b, [line(p)])
    assert action(c, order, "reserve").status_code == 200
    # Move expiry into the future of the pre-existing order, but before current time.
    from app.models import Order

    cutoff = now() - timedelta(days=4)
    with Session(engine()) as db:
        db.get(Order, order["id"]).created_at = cutoff - timedelta(days=1)
        db.commit()
    project([interval(start=cutoff - timedelta(days=30), end=cutoff)])
    assert (
        c.put(
            "/api/v1/orders/" + order["id"] + "/lines",
            json={"request_key": str(uuid4()), "lines": [line(p, 2)]},
        ).status_code
        == 402
    )
    assert (
        c.post(
            "/api/v1/orders",
            json={"request_key": str(uuid4()), "buyer_id": b["id"], "lines": [line(p)]},
        ).status_code
        == 402
    )
    r = c.post(
        "/api/v1/orders/" + order["id"] + "/complete",
        json={"request_key": str(uuid4()), "confirm_received": True},
    )
    assert r.status_code == 200, r.text
    assert c.get("/api/v1/parts/" + p["id"]).json()["quantity"] == 2


def test_vin_and_global_entry_points_share_capacity(pilot, monkeypatch):
    c, w, _ = pilot
    for i in range(10):
        assert c.post("/api/v1/vehicles", json=vehicle(i)).status_code == 201
    assert (
        c.post(
            "/api/v1/vehicles", json={**vehicle(55), "vin": "YV4L12RK6N1970668"}
        ).status_code
        == 409
    )
    from app.services.unified_catalogue import CatalogueAdapter
    from test_unified_catalogue import envelope

    monkeypatch.setattr(CatalogueAdapter, "plan", lambda *args, **kwargs: envelope())
    monkeypatch.setattr(
        CatalogueAdapter,
        "directory",
        lambda *args, **kwargs: dict(
            items=[
                dict(
                    source_modification_id=107555,
                    model_id=13084,
                    manufacturer_id=120,
                    manufacturer="Synthetic",
                    model="Model",
                    snapshot_sha="a" * 64,
                )
            ]
        ),
    )
    r = c.post(
        "/api/v1/vehicles/catalogue-directory/vehicles",
        json={
            "request_key": str(uuid4()),
            "source_modification_id": 107555,
            "year": 2018,
        },
    )
    assert r.status_code == 409, r.text
    assert c.get("/api/v1/vehicles").json()["total"] == 10


def test_dry_run_and_staff_finance_isolation(pilot):
    c, w, project = pilot
    project([], mode="dry_run")
    assert c.post("/api/v1/vehicles", json=vehicle(1)).status_code == 201
    assert (
        "vehicle.create" in c.get("/api/v1/billing/entitlements").json()["would_block"]
    )
    from app.services.auth import hasher

    with Session(engine()) as db:
        db.add(
            Account(
                name="Staff",
                email="staff-phase2@example.test",
                password_hash=hasher.hash("staff-fixture-password"),
                role="MANAGER",
                workspace_account_id=w,
                permissions=["inventory.view"],
                is_active=True,
            )
        )
        db.commit()
    c.post("/api/v1/auth/logout")
    r = c.post(
        "/api/v1/auth/login",
        json={
            "email": "staff-phase2@example.test",
            "password": "staff-fixture-password",
        },
    )
    assert r.status_code == 200
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    assert c.post("/api/v1/billing/trial", json={"plan": "standard"}).status_code == 403
    assert c.post("/api/v1/billing/bind").status_code == 403
    assert c.get("/api/v1/billing/payments").status_code == 403
    data = c.get("/api/v1/billing/entitlements").json()
    assert (
        not data["can_manage"]
        and "plans" not in data
        and data["usage"]["employees"] is None
    )


def test_two_concurrent_trial_claims_have_one_winner(pilot):
    c, w, project = pilot
    project([])
    from bot.billing.models import BillingError

    with Session(engine()) as db:
        account = db.get(EntitlementWorkspace, w).billing_account_id

    def claim(_):
        try:
            e.local_bridge().trial(w, account, "standard")
            return 200
        except BillingError:
            return 409

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(claim, [1, 2])) == [200, 409]


def test_expired_get_cannot_provision_new_catalogue(pilot):
    c, w, project = pilot
    v = c.post("/api/v1/vehicles", json=vehicle(72)).json()
    project([])
    r = c.get(
        "/api/v1/plan-parts/donor-parts/classification/preview",
        params={"vehicle_id": v["id"], "ktype": 123, "provision": True},
    )
    assert r.status_code == 402, r.text
