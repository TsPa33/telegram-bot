from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from subprocess import run
import pytest
import sys
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.db import engine
from app.main import app
from app.models import Account, Session as LoginSession, now
from conftest import signup


def op(c, part, type, quantity=0, **kwargs):
    return c.post(
        f"/api/v1/parts/{part['id']}/operations",
        json={
            "type": type,
            "quantity": quantity,
            "reason": "Test operation reason",
            **kwargs,
        },
    )


def test_authentication_and_csrf(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    signup(client)
    assert client.get("/api/v1/auth/me").json()["email"] == "owner@example.test"
    with Session(engine()) as db:
        assert db.scalar(select(Account)).password_hash.startswith("$argon2id$")
        assert db.scalar(select(LoginSession)).token_hash != client.cookies.get(
            "warehouse_session"
        )
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.test", "password": "wrong-password-123"},
        ).status_code
        == 401
    )
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.test", "password": "a-long-test-password"},
    )
    assert r.status_code == 200
    assert "HttpOnly" in r.headers.get_list("set-cookie")[0]


def test_expired_session(logged):
    with Session(engine()) as db:
        db.scalar(select(LoginSession)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert logged.get("/api/v1/auth/me").status_code == 401


def test_auth_validation_and_rate_limit(client):
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "bad", "password": "short", "name": "X"},
        ).status_code
        == 422
    )
    for _ in range(20):
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "absent@example.test", "password": "wrong-password-123"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "absent@example.test", "password": "wrong-password-123"},
        ).status_code
        == 429
    )


def test_vehicle_crud(logged, vehicle, vehicle_data):
    id = vehicle["id"]
    assert logged.get(f"/api/v1/vehicles/{id}").json()["donor_id"] == "TEST-1"
    assert logged.get("/api/v1/vehicles?q=TEST").json()["total"] == 1
    assert (
        logged.put(
            f"/api/v1/vehicles/{id}", json={**vehicle_data, "notes": "Updated"}
        ).json()["notes"]
        == "Updated"
    )
    assert logged.post("/api/v1/vehicles", json=vehicle_data).status_code == 409
    assert (
        logged.post("/api/v1/vehicles", json={**vehicle_data, "year": 100}).status_code
        == 422
    )
    assert logged.post(f"/api/v1/archive/vehicles/{id}").status_code == 200
    assert logged.get("/api/v1/vehicles").json()["total"] == 0
    assert logged.get("/api/v1/archive?entity=vehicles").json()["total"] == 1
    assert logged.post(f"/api/v1/archive/vehicles/{id}?restore=true").status_code == 200


def test_tenant_isolation(logged, vehicle, part, catalog):
    assert logged.post("/api/v1/categories/import", json=catalog).status_code == 200
    cat = logged.get("/api/v1/categories").json()["items"][0]
    with TestClient(app) as other:
        signup(other, "other@example.test")
        for resource in ["parts", "vehicles", "audit", "categories"]:
            assert other.get("/api/v1/" + resource).json()["total"] == 0
        for path in [
            f"vehicles/{vehicle['id']}",
            f"vehicles/{vehicle['id']}/analytics",
            f"parts/{part['id']}",
        ]:
            assert other.get("/api/v1/" + path).status_code == 404
        assert (
            other.post(
                "/api/v1/parts", json={"name": "X", "vehicle_id": vehicle["id"]}
            ).status_code
            == 404
        )
        assert (
            other.post(
                "/api/v1/parts", json={"name": "X", "category_id": cat["id"]}
            ).status_code
            == 404
        )
        assert op(other, part, "receipt", 1).status_code == 404
        assert (
            other.post(f"/api/v1/vehicles/{vehicle['id']}/checklist").status_code == 404
        )
        assert other.post(f"/api/v1/archive/parts/{part['id']}").status_code == 404


def test_category_import_hierarchy_and_idempotence(logged, catalog):
    assert (
        logged.post("/api/v1/categories/import?dry_run=true", json=catalog).json()[
            "created"
        ]
        == 5
    )
    assert logged.get("/api/v1/categories").json()["total"] == 0
    assert logged.post("/api/v1/categories/import", json=catalog).json()["created"] == 5
    rows = logged.get("/api/v1/categories").json()["items"]
    twins = [r for r in rows if r["name"] == "Same name"]
    assert len(twins) == 2 and twins[0]["parent_id"] != twins[1]["parent_id"]
    ids = {r["id"] for r in rows}
    assert logged.post("/api/v1/categories/import", json=catalog).json()["created"] == 0
    assert {r["id"] for r in logged.get("/api/v1/categories").json()["items"]} == ids
    bad = {
        "source": "bad",
        "nodes": [
            {"key": "a", "parent_key": "b", "name": "A", "kind": "category"},
            {"key": "b", "parent_key": "a", "name": "B", "kind": "category"},
        ],
    }
    assert logged.post("/api/v1/categories/import", json=bad).status_code == 422
    changed = {
        **catalog,
        "nodes": [
            {**n, "name": "Changed"} if n["key"] == "a" else n for n in catalog["nodes"]
        ],
    }
    assert logged.post("/api/v1/categories/import", json=changed).status_code == 409
    assert logged.get("/api/v1/categories").json()["total"] == 5


def test_import_file_rejects_ambiguous_text(logged):
    assert (
        logged.post(
            "/api/v1/categories/import-file",
            files={"file": ("raw.txt", b"Unstructured raw tree")},
        ).status_code
        == 422
    )
    assert (
        logged.post(
            "/api/v1/categories/import-file", files={"file": ("raw.json", b"\xff\xfe")}
        ).status_code
        == 422
    )


def test_checklist_preserves_work(logged, vehicle, catalog):
    path = f"/api/v1/vehicles/{vehicle['id']}/checklist"
    assert logged.post(path).status_code == 409
    logged.post("/api/v1/categories/import", json=catalog)
    assert logged.post(path).json()["created"] == 1
    part = logged.get("/api/v1/parts").json()["items"][0]
    assert part["quantity"] == 0 and part["availability"] == "unchecked"
    assert part["selling_price"] is None and part["oem_number"] == ""
    assert op(logged, part, "receipt", 3).status_code == 200
    assert logged.post(path).json()["created"] == 0
    assert logged.get(f"/api/v1/parts/{part['id']}").json()["quantity"] == 3
    assert logged.post(f"/api/v1/archive/parts/{part['id']}").status_code == 200
    assert logged.post(path).json()["created"] == 0


def test_stock_consistency_reservations_and_writeoff(logged, part):
    assert op(logged, part, "receipt", 5).json()["available_quantity"] == 5
    assert op(logged, part, "reserve", 3).json()["available_quantity"] == 2
    assert op(logged, part, "reserve", 3).status_code == 409
    assert op(logged, part, "write_off", 3).status_code == 409
    assert op(logged, part, "write_off", 2).json()["quantity"] == 3
    assert op(logged, part, "release", 4).status_code == 409
    assert op(logged, part, "release", 3).json()["reserved_quantity"] == 0
    assert op(logged, part, "correction", 1).json()["quantity"] == 1
    assert op(logged, part, "transfer", location="A-02").json()["location"] == "A-02"
    assert op(logged, part, "receipt", 0).status_code == 422
    assert op(logged, part, "correction", -1).status_code == 422
    assert (
        logged.put(
            f"/api/v1/parts/{part['id']}", json={"name": "X", "quantity": 999}
        ).status_code
        == 422
    )


def test_concurrent_reservations(logged, part):
    op(logged, part, "receipt", 1)
    cookies, csrf = dict(logged.cookies), logged.headers["X-CSRF-Token"]

    def reserve(_):
        with TestClient(app) as c:
            c.cookies.update(cookies)
            c.headers["X-CSRF-Token"] = csrf
            return op(c, part, "reserve", 1).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [200, 409]
    assert logged.get(f"/api/v1/parts/{part['id']}").json()["reserved_quantity"] == 1


def test_audit_immutable_and_filters(logged, part, vehicle):
    op(logged, part, "receipt", 2)
    data = logged.get(
        "/api/v1/audit",
        params={"type": "receipt", "part_id": part["id"], "vehicle_id": vehicle["id"]},
    ).json()
    assert data["total"] == 1
    event = data["items"][0]
    assert event["before"]["quantity"] == 0 and event["after"]["quantity"] == 2
    assert event["actor_id"] and event["created_at"] and event["reason"]
    assert logged.delete(f"/api/v1/audit/{event['id']}").status_code in (404, 405)
    with engine().connect() as conn:
        for sql in [
            "UPDATE operations SET reason = :r WHERE id = :id",
            "DELETE FROM operations WHERE id = :id",
        ]:
            with pytest.raises(DBAPIError):
                conn.execute(text(sql), {"r": "tamper", "id": event["id"]})
            conn.rollback()


def test_archive_and_atomic_bulk(logged, part):
    p2 = logged.post("/api/v1/parts", json={"name": "Other test part"}).json()
    op(logged, part, "receipt", 1)
    op(logged, part, "reserve", 1)
    assert (
        logged.post(
            "/api/v1/parts/bulk-actions",
            json={
                "ids": [part["id"], p2["id"]],
                "action": "archive",
                "reason": "Test archive",
            },
        ).status_code
        == 409
    )
    assert logged.get("/api/v1/parts").json()["total"] == 2
    op(logged, part, "release", 1)
    assert (
        logged.post(
            "/api/v1/parts/bulk-actions",
            json={
                "ids": [part["id"], p2["id"]],
                "action": "archive",
                "reason": "Test archive",
            },
        ).json()["updated"]
        == 2
    )
    assert logged.get("/api/v1/archive").json()["total"] == 2
    assert op(logged, part, "receipt", 1).status_code == 409
    assert (
        logged.post(f"/api/v1/archive/parts/{part['id']}?restore=true").status_code
        == 200
    )
    assert logged.get(f"/api/v1/parts/{part['id']}").json()["quantity"] == 1
    assert logged.get("/api/v1/audit?type=receipt").json()["total"] == 1


def test_dashboard_real_values(logged, part, vehicle):
    assert op(logged, part, "receipt", 3).status_code == 200
    op(logged, part, "reserve", 1)
    r = logged.get("/api/v1/dashboard")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["vehicles"] == 1 and d["positions"] == 1
    assert (
        d["stock_units"] == 3 and d["available_units"] == 2 and d["reserved_units"] == 1
    )
    assert float(d["estimated_sales_value"]) == 150
    assert float(d["potential_gross_margin"]) == 90
    assert float(d["vehicle_acquisition_cost"]) == 100
    assert len(d["by_vehicle"]) == 1
    assert (
        logged.get(f"/api/v1/vehicles/{vehicle['id']}/analytics").json()["stock_units"]
        == 3
    )


def test_empty_dashboard_and_protected_routes(logged):
    d = logged.get("/api/v1/dashboard").json()
    assert (
        d["positions"] == 0
        and d["vehicles"] == 0
        and float(d["estimated_sales_value"]) == 0
    )
    with TestClient(app) as unauth:
        for path in [
            "dashboard",
            "vehicles",
            "categories",
            "parts",
            "inventory",
            "audit",
            "archive",
            "settings",
        ]:
            assert unauth.get("/api/v1/" + path).status_code == 401
        assert unauth.post("/api/v1/parts", json={"name": "X"}).status_code == 401


def test_individual_tracking(logged):
    part = logged.post(
        "/api/v1/parts",
        json={
            "name": "Tracked",
            "individually_tracked": True,
            "serial_number": "TEST-SERIAL",
        },
    ).json()
    assert op(logged, part, "receipt", 2).status_code == 409
    assert op(logged, part, "receipt", 1).status_code == 200
    assert (
        logged.post(
            "/api/v1/parts", json={"name": "Tracked", "individually_tracked": True}
        ).status_code
        == 422
    )


def test_migrations_roundtrip():
    alembic = [sys.executable, "-m", "alembic"]
    run([*alembic, "downgrade", "base"], check=True)
    assert "parts" not in inspect(engine()).get_table_names()
    run([*alembic, "upgrade", "head"], check=True)
    assert {
        "accounts",
        "sessions",
        "vehicles",
        "categories",
        "parts",
        "operations",
        "photos",
    } <= set(inspect(engine()).get_table_names())
    run([*alembic, "check"], check=True)


def test_photo_storage_and_isolation(logged, part, tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image

    monkeypatch.setenv("WAREHOUSE_PHOTO_DIR", str(tmp_path))
    assert logged.get("/api/v1/settings").json()["photos_enabled"]
    path = f"/api/v1/parts/{part['id']}/photos"
    assert (
        logged.post(
            path, files={"file": ("bad.jpg", b"not an image", "image/jpeg")}
        ).status_code
        == 422
    )
    image = BytesIO()
    Image.new("RGB", (4, 4), "white").save(image, format="PNG")
    r = logged.post(path, files={"file": ("sample.png", image.getvalue(), "image/png")})
    assert r.status_code == 201, r.text
    assert len(logged.get(path).json()) == 1
    url = r.json()["url"]
    assert logged.get(url).headers["content-type"] == "image/jpeg"
    with TestClient(app) as other:
        signup(other, "photo-other@example.test")
        assert other.get(url).status_code == 404
        assert other.get(path).status_code == 404


def test_category_parent_validation_and_archival(logged, vehicle, catalog):
    logged.post("/api/v1/categories/import", json=catalog)
    cats = {
        r["external_key"]: r for r in logged.get("/api/v1/categories").json()["items"]
    }
    assert (
        logged.post(
            "/api/v1/parts",
            json={
                "name": "Mismatch",
                "category_id": cats["b"]["id"],
                "subcategory_id": cats["a-1"]["id"],
            },
        ).status_code
        == 422
    )
    assert (
        logged.post(f"/api/v1/archive/categories/{cats['a']['id']}").status_code == 200
    )
    assert logged.post(f"/api/v1/vehicles/{vehicle['id']}/checklist").status_code == 409
    assert (
        logged.post(
            f"/api/v1/archive/categories/{cats['a']['id']}?restore=true"
        ).status_code
        == 200
    )
    assert (
        logged.post(f"/api/v1/vehicles/{vehicle['id']}/checklist").json()["created"]
        == 1
    )


def test_audit_date_filter_and_pagination(logged, part):
    op(logged, part, "receipt", 1)
    assert (
        logged.get("/api/v1/audit?date_from=2100-01-01T00:00:00Z").json()["total"] == 0
    )
    assert logged.get("/api/v1/audit?date_to=2000-01-01T00:00:00Z").json()["total"] == 0
    result = logged.get("/api/v1/audit?limit=1").json()
    assert result["total"] == 3 and len(result["items"]) == 1
    assert logged.get("/api/v1/parts?limit=0").status_code == 422
