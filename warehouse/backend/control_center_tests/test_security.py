import time
from datetime import timedelta
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session as DBSession
from app.control_center.models import (
    Audit,
    Company,
    Grant,
    Note,
    Session,
    Staff,
    Task,
    SourceLink,
    now,
)
from app.control_center.security import digest, totp, mfa_step
from app.control_center.config import connection
from test_support import authenticate, SECRET


def company(db, name="Company", workspace="workspace-1", env="local"):
    c = Company(
        environment=env,
        workspace_id=workspace,
        display_name=name,
        search_text=(name + " owner@private.test").lower(),
        registered_at=now(),
        fetched_at=now(),
        snapshot={
            "people": [
                {
                    "id": "owner",
                    "name": "Owner",
                    "email": "owner@private.test",
                    "role": "DIRECTOR",
                    "active": True,
                }
            ],
            "access": {"status": "TRIAL"},
            "binding": None,
        },
    )
    db.add(c)
    db.commit()
    return c


def test_customer_cookie_is_not_staff_and_flag_off(client, monkeypatch):
    client.cookies.set("warehouse_session", "customer-director")
    assert client.get("/api/control/companies").status_code == 401
    monkeypatch.setenv("CONTROL_CENTER_ENABLED", "false")
    assert client.get("/api/control/status").status_code == 404
    assert client.post("/api/control/auth/login", json={}).status_code == 404


def test_mfa_required_origin_and_replay(client, staff_factory):
    owner = staff_factory()
    body = dict(
        username=owner.username, password="long-staff-test-password", code="000000"
    )
    assert (
        client.post(
            "/api/control/auth/login",
            json=body,
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    assert client.post("/api/control/auth/login", json=body).status_code == 401
    r = authenticate(client, owner)
    assert (
        "Path=/api/control" in r.headers["set-cookie"]
        and "HttpOnly" in r.headers["set-cookie"]
    )
    assert client.get("/api/control/auth/me").status_code == 200
    body["code"] = totp(SECRET, int(time.time()) // 30)
    assert client.post("/api/control/auth/login", json=body).status_code == 401


def test_logout_revokes_copied_server_session(client, staff_factory, db):
    authenticate(client, staff_factory())
    token = client.cookies.get("carpot_control_session")
    assert (
        client.post(
            "/api/control/auth/logout", headers={"X-Control-CSRF": "bad"}
        ).status_code
        == 403
    )
    assert client.post("/api/control/auth/logout").status_code == 204
    assert db.get(Session, digest(token)) is None
    client.cookies.set("carpot_control_session", token, path="/api/control")
    assert client.get("/api/control/auth/me").status_code == 401


@pytest.mark.parametrize("role", ["Manager", "Support"])
def test_scope_list_search_detail_notes_finance(client, staff_factory, db, role):
    me = staff_factory(role)
    a, b = company(db, "Allowed", "a"), company(db, "Secret", "b")
    db.add(Grant(company_id=a.id, staff_id=me.id))
    db.commit()
    authenticate(client, me)
    assert [r["id"] for r in client.get("/api/control/companies").json()["items"]] == [
        a.id
    ]
    assert client.get("/api/control/companies?q=Secret").json()["items"] == []
    for suffix in ["", "/notes", "/finance"]:
        assert client.get("/api/control/companies/" + b.id + suffix).status_code == 404
    assert (
        client.post(
            "/api/control/companies/" + b.id + "/notes", json={"text": "foreign"}
        ).status_code
        == 404
    )
    assert client.get("/api/control/companies/" + a.id + "/finance").status_code == 403
    detail = client.get("/api/control/companies/" + a.id).json()
    assert detail["people"][0]["email"] == "o***@private.test"
    assert "amount_minor" not in str(detail)
    assert client.get("/api/control/companies?limit=101").status_code == 422
    assert (
        client.post(
            "/api/control/companies/" + a.id + "/assign", json={"staff_id": me.id}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("active,role", [(False, "Manager"), (True, "Support")])
def test_role_change_deactivation_revoke(client, staff_factory, db, active, role):
    owner, target = staff_factory(), staff_factory("Manager")
    authenticate(client, owner)
    token = "target-stolen-session"
    db.add(
        Session(
            token_hash=digest(token),
            staff_id=target.id,
            csrf_hash=digest("csrf"),
            audience="carpot-control-center",
            mfa_verified=True,
            expires_at=now() + timedelta(hours=1),
        )
    )
    db.commit()
    r = client.patch(
        "/api/control/staff/" + target.id,
        json=dict(
            role=role,
            active=active,
            finance=False,
            reason="review access",
            mfa_code=totp(SECRET, int(time.time()) // 30 + 1),
        ),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Session, digest(token)) is None
    assert (
        db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.permission == "staff.update")
        )
        == 1
    )


def test_notes_tasks_atomic_audit_no_source_write(client, staff_factory, db):
    owner = staff_factory()
    c = company(db)
    authenticate(client, owner)
    result = client.post(
        "/api/control/companies/" + c.id + "/notes",
        json={"text": "Internal <script>never send</script>"},
    )
    assert result.status_code == 201, result.text
    assert db.scalar(select(func.count()).select_from(Note)) == 1
    audit = db.scalar(select(Audit).where(Audit.permission == "notes.write"))
    assert audit.target == result.json()["id"] and "Internal" not in str(
        audit.safe_diff
    )
    result = client.post(
        "/api/control/companies/" + c.id + "/tasks",
        json=dict(
            next_action="Call only after review",
            status="open",
            due_at="2026-12-01T12:00:00Z",
        ),
    )
    assert result.status_code == 201
    assert (
        client.patch(
            "/api/control/tasks/" + result.json()["id"],
            json=dict(next_action="Review", status="done"),
        ).status_code
        == 200
    )
    assert client.get("/api/control/tasks").json()[0]["status"] == "done"
    # A failed audit insert rolls back its note transaction; no silent partial commit.
    with db.bind.begin() as cdb:
        cdb.execute(text("REVOKE INSERT ON control_center.audit FROM cc_app"))
    result = client.post(
        "/api/control/companies/" + c.id + "/notes", json={"text": "Must roll back"}
    )
    assert result.status_code == 503
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Note)) == 1


def test_durable_throttle(client, staff_factory):
    owner = staff_factory()
    for _ in range(12):
        assert (
            client.post(
                "/api/control/auth/login",
                json=dict(username=owner.username, password="bad", code="000000"),
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/control/auth/login",
            json=dict(username=owner.username, password="bad", code="000000"),
        ).status_code
        == 429
    )


def test_audience_and_mfa_marker_enforced(client, staff_factory, db):
    staff = staff_factory()
    token = "bad-audience"
    row = Session(
        token_hash=digest(token),
        staff_id=staff.id,
        csrf_hash=digest("x"),
        audience="warehouse",
        mfa_verified=True,
        expires_at=now() + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    client.cookies.set("carpot_control_session", token, path="/api/control")
    assert client.get("/api/control/auth/me").status_code == 401
    row.audience = "carpot-control-center"
    row.mfa_verified = False
    db.commit()
    assert client.get("/api/control/auth/me").status_code == 401


def test_rfc_totp_and_no_role_escalation(client, staff_factory, db):
    assert totp(SECRET, 59 // 30) == "287082"  # RFC6238 SHA1 8-digit vector modulo 1e6
    assert mfa_step(SECRET, "287082", stamp=59) == 1
    assert mfa_step(SECRET, "287082", last=1, stamp=59) is None
    manager = staff_factory("Manager")
    owner = staff_factory()
    authenticate(client, manager)
    assert (
        client.patch(
            "/api/control/staff/" + owner.id,
            json=dict(role="Manager", active=False, reason="attack"),
        ).status_code
        == 403
    )
    assert client.post("/api/control/auth/register", json={}).status_code == 404
    assert client.post("/api/control/companies/x/refund", json={}).status_code == 404


def test_cursor_ties_and_environment_isolation(client, staff_factory, db):
    owner = staff_factory()
    a = company(db, "Same", "a")
    b = company(db, "Same", "b")
    foreign = company(db, "Other", "c", "production")
    authenticate(client, owner)
    first = client.get("/api/control/companies?limit=1").json()
    second = client.get(
        "/api/control/companies", params={"limit": 1, "cursor": first["next_cursor"]}
    ).json()
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {a.id, b.id}
    assert client.get("/api/control/companies/" + foreign.id).status_code == 404
    assert (
        client.get(
            "/api/control/companies",
            params={"cursor": first["next_cursor"], "q": "changed"},
        ).status_code
        == 422
    )


def test_unavailable_not_zero_and_billing_failure(client, staff_factory, db):
    authenticate(client, staff_factory())
    c = company(db)
    o = client.get("/api/control/overview").json()
    assert o["workspaces"] is None and o["metrics"]["mrr"]["state"] == "unavailable"
    assert (
        client.get("/api/control/companies/" + c.id + "/finance").json()["state"]
        == "unavailable"
    )
    assert client.get("/api/control/companies").status_code == 200


def test_reassignment_revokes_old_company_scope(client, staff_factory, db):
    owner = staff_factory()
    first = staff_factory("Manager", "first")
    second = staff_factory("Manager", "second")
    c = company(db)
    authenticate(client, owner)
    assert (
        client.post(
            "/api/control/companies/" + c.id + "/assign", json={"staff_id": first.id}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/control/companies/" + c.id + "/assign", json={"staff_id": second.id}
        ).status_code
        == 200
    )
    db.expire_all()
    assert db.get(Grant, (c.id, first.id)) is None and db.get(Grant, (c.id, second.id))
    assert (
        db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.permission == "assignments.write")
        )
        == 2
    )


def test_support_override_cannot_expose_financial_amounts(client, staff_factory, db):
    staff = staff_factory("Support", finance=True)
    c = company(db)
    c.snapshot = {
        **c.snapshot,
        "access": {
            "status": "ACTIVE",
            "amount_minor": 999999,
            "raw_provider_payload": "private",
        },
    }
    db.add(Grant(company_id=c.id, staff_id=staff.id))
    db.commit()
    authenticate(client, staff)
    r = client.get("/api/control/companies/" + c.id)
    assert "amount_minor" not in r.text and "raw_provider_payload" not in r.text
    assert client.get("/api/control/companies/" + c.id + "/finance").status_code == 403
    assert client.get("/api/control/exports").status_code == 404


def test_operator_password_reset_revokes_sessions(client, staff_factory, db):
    staff = staff_factory()
    authenticate(client, staff)
    from app.control_center.manage import reset_password

    reset_password(db, staff.username, "new-long-staff-password")
    assert client.get("/api/control/auth/me").status_code == 401
    assert (
        db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.permission == "staff.password_reset")
        )
        == 1
    )


def test_flag_off_keeps_customer_routes_and_lazy_dependencies(monkeypatch):
    import os, subprocess, sys

    env = {**os.environ, "CONTROL_CENTER_ENABLED": "false"}
    script = """
import sys
from app.main import app
from fastapi.testclient import TestClient
assert 'app.control_center.api' not in sys.modules
client=TestClient(app)
assert client.get('/api/control/status').status_code == 404
assert client.get('/api/v1/auth/options').status_code == 200
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_missing_configuration_fails_closed_without_secret_details(
    client, staff_factory, monkeypatch
):
    staff = staff_factory()
    monkeypatch.delenv("CONTROL_CENTER_MFA_KEY")
    response = client.post(
        "/api/control/auth/login",
        json=dict(
            username=staff.username,
            password="long-staff-test-password",
            code=totp(SECRET, int(time.time()) // 30),
        ),
    )
    assert response.status_code == 503 and "CONTROL_CENTER_MFA_KEY" not in response.text
    monkeypatch.setenv("CONTROL_CENTER_ORIGIN", "invalid-origin")
    assert client.get("/api/control/status").status_code == 503


def test_concurrent_reassignment_keeps_only_final_manager(client, staff_factory, db):
    """Two independent staff sessions contend for the same real PostgreSQL row."""
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient

    owner = staff_factory("Owner", "assign-owner")
    admin = staff_factory("Administrator", "assign-admin")
    old = staff_factory("Manager", "assign-old")
    first = staff_factory("Manager", "assign-first")
    second = staff_factory("Manager", "assign-second")
    support = staff_factory("Support", "assign-support")
    c = company(db)
    authenticate(client, owner)
    path = "/api/control/companies/" + c.id + "/assign"
    assert client.post(path, json={"staff_id": old.id}).status_code == 200
    assert client.post(path, json={"staff_id": support.id}).status_code == 200
    with TestClient(
        client.app,
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    ) as other:
        authenticate(other, admin)
        with ThreadPoolExecutor(max_workers=2) as pool:
            # Force both requests into the race, without relying on a sleep to
            # assume they reached the critical section. The runtime pool has 2 slots.
            with db.bind.begin() as blocker:
                blocker.execute(
                    text(
                        "SELECT id FROM control_center.companies WHERE id=:id FOR NO KEY UPDATE"
                    ),
                    {"id": c.id},
                )
                futures = [
                    pool.submit(client.post, path, json={"staff_id": first.id}),
                    pool.submit(other.post, path, json={"staff_id": second.id}),
                ]
                deadline = time.monotonic() + 2
                waiting = 0
                while time.monotonic() < deadline:
                    blocker.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = blocker.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                            "AND usename='cc_app' AND wait_event_type='Lock'"
                        )
                    )
                    if waiting >= 2:
                        break
                    time.sleep(0.02)
            assert waiting >= 2, "Both API requests must actually contend"
            for future in futures:
                response = future.result(timeout=10)
                assert response.status_code == 200, response.text
    db.expire_all()
    winner = db.get(Company, c.id).manager_id
    assert winner in {first.id, second.id}
    loser = second if winner == first.id else first
    assert set(db.scalars(select(Grant.staff_id).where(Grant.company_id == c.id))) == {
        winner,
        support.id,
    }
    assert (
        db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.permission == "assignments.write")
        )
        == 4
    )
    for person, expected in [
        (old, 404),
        (loser, 404),
        (first if winner == first.id else second, 200),
        (support, 200),
    ]:
        with TestClient(
            client.app,
            base_url="http://testserver",
            headers={"Origin": "http://testserver"},
        ) as scoped:
            authenticate(scoped, person)
            assert scoped.get("/api/control/companies/" + c.id).status_code == expected


def test_role_change_does_not_inherit_company_grants(
    client, staff_factory, db, monkeypatch
):
    owner = staff_factory()
    manager = staff_factory("Manager", "role-manager")
    support = staff_factory("Support", "role-support")
    c = company(db)
    authenticate(client, owner)
    path = "/api/control/companies/" + c.id + "/assign"
    assert client.post(path, json={"staff_id": owner.id}).status_code == 422
    assert client.post(path, json={"staff_id": manager.id}).status_code == 200
    assert client.post(path, json={"staff_id": support.id}).status_code == 200
    stamp = time.time()
    for index, (target, role) in enumerate(
        [(support, "Manager"), (manager, "Support")]
    ):
        monkeypatch.setattr(time, "time", lambda: stamp + (index + 1) * 30)
        response = client.patch(
            "/api/control/staff/" + target.id,
            json=dict(
                role=role,
                active=True,
                finance=False,
                reason="role changed",
                mfa_code=totp(SECRET, int(time.time()) // 30),
            ),
        )
        assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Company, c.id).manager_id is None
    assert list(db.scalars(select(Grant).where(Grant.company_id == c.id))) == []
    from fastapi.testclient import TestClient

    for person in (manager, support):
        with TestClient(
            client.app,
            base_url="http://testserver",
            headers={"Origin": "http://testserver"},
        ) as scoped:
            authenticate(scoped, person)
            assert scoped.get("/api/control/companies/" + c.id).status_code == 404


def test_csrf_recovery_for_existing_session_and_logout(client, staff_factory, db):
    owner = staff_factory()
    authenticate(client, owner)
    token = client.cookies.get("carpot_control_session")
    session = db.get(Session, digest(token))
    # Simulate the original random-proof session used before this upgrade.
    session.csrf_hash = digest("old-random-proof")
    db.commit()
    assert (
        client.post(
            "/api/control/auth/enrollment", headers={"X-Control-CSRF": ""}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/control/auth/logout", headers={"X-Control-CSRF": "wrong"}
        ).status_code
        == 403
    )
    for headers in (
        {"Origin": "https://evil.test"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "cross-site"},
    ):
        assert client.get("/api/control/auth/csrf", headers=headers).status_code == 403
    recovered = client.get("/api/control/auth/csrf")
    assert recovered.status_code == 200
    assert recovered.headers["cache-control"] == "no-store"
    proof = recovered.json()["csrf"]
    assert recovered.json()["staff_id"] == owner.id
    assert proof != token and token not in recovered.text
    assert client.get("/api/control/auth/csrf").json()["csrf"] == proof
    assert (
        client.post(
            "/api/control/auth/enrollment",
            headers={"X-Control-CSRF": "old-random-proof"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/control/auth/enrollment", headers={"X-Control-CSRF": proof}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/control/auth/logout", headers={"X-Control-CSRF": proof}
        ).status_code
        == 204
    )
    assert client.get("/api/control/auth/csrf").status_code == 401
    client.cookies.set("carpot_control_session", token, path="/api/control")
    assert client.get("/api/control/auth/csrf").status_code == 401


def test_privilege_change_requires_fresh_single_use_mfa(client, staff_factory, db):
    owner, target = staff_factory(), staff_factory("Manager")
    authenticate(client, owner)
    body = dict(
        role="Administrator", active=True, finance=True, reason="Approved access"
    )
    path = "/api/control/staff/" + target.id
    assert client.patch(path, json=body).status_code == 403
    db.refresh(owner)
    replay = totp(SECRET, owner.last_totp_step)
    assert client.patch(path, json=dict(body, mfa_code=replay)).status_code == 403
    db.expire_all()
    assert db.get(Staff, target.id).role == "Manager"
    fresh = totp(SECRET, owner.last_totp_step + 1)
    assert client.patch(path, json=dict(body, mfa_code=fresh)).status_code == 200
    assert client.patch(path, json=dict(body, mfa_code=fresh)).status_code == 403
    assert (
        db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.permission == "staff.update")
        )
        == 1
    )
    assert fresh not in str([a.safe_diff for a in db.scalars(select(Audit))])


def test_csrf_recovery_bound_to_expected_staff(client, staff_factory, db):
    owner = staff_factory()
    authenticate(client, owner)
    c = company(db)
    assert (
        client.get(
            "/api/control/companies/" + c.id,
            headers={"X-Control-Staff": "different-staff"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/control/auth/csrf", headers={"X-Control-Staff": "different-staff"}
        ).status_code
        == 401
    )
    recovered = client.get(
        "/api/control/auth/csrf", headers={"X-Control-Staff": owner.id}
    )
    assert recovered.status_code == 200 and recovered.json()["staff_id"] == owner.id
    client.headers["X-Control-CSRF"] = recovered.json()["csrf"]
    assert (
        client.post(
            "/api/control/companies/" + c.id + "/notes",
            json={"text": "new tab"},
            headers={"X-Control-Staff": owner.id},
        ).status_code
        == 201
    )


@pytest.mark.parametrize("second_action", ["reassign", "revoked_note"])
def test_concurrent_assignment_never_leaves_stale_manager_scope(
    client, staff_factory, db, second_action
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy import event
    from fastapi.testclient import TestClient

    first_owner = staff_factory("Owner", "owner-one")
    second_owner = staff_factory("Owner", "owner-two")
    old = staff_factory("Manager", "old-manager")
    new = staff_factory("Manager", "new-manager")
    last = staff_factory("Manager", "last-manager")
    c = company(db)
    c.manager_id = old.id
    db.add(Grant(company_id=c.id, staff_id=old.id))
    db.commit()
    authenticate(client, first_owner)
    with TestClient(
        client.app,
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    ) as other:
        authenticate(other, second_owner if second_action == "reassign" else old)
        first_deleted, release = Event(), Event()

        def pause(conn, cursor, statement, params, context, many):
            if not first_deleted.is_set() and statement.startswith(
                "DELETE FROM control_center.company_grants"
            ):
                first_deleted.set()
                if not release.wait(8):
                    raise AssertionError(
                        "Concurrent request did not finish synchronization"
                    )

        runtime = connection()
        event.listen(runtime, "after_cursor_execute", pause)

        def first():
            return client.post(
                "/api/control/companies/" + c.id + "/assign", json={"staff_id": new.id}
            )

        def second():
            if second_action == "reassign":
                return other.post(
                    "/api/control/companies/" + c.id + "/assign",
                    json={"staff_id": last.id},
                )
            return other.post(
                "/api/control/companies/" + c.id + "/notes",
                json={"text": "Revoked write must not commit"},
            )

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                one = pool.submit(first)
                assert first_deleted.wait(5)
                two = pool.submit(second)
                try:
                    deadline = time.monotonic() + 2
                    observed = False
                    # Observe actual PostgreSQL contention, rather than assume a scheduler delay.
                    while time.monotonic() < deadline:
                        with db.bind.connect() as probe:
                            waiting = probe.scalar(
                                text(
                                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%control_center.%'"
                                )
                            )
                        if waiting or two.done():
                            observed = True
                            break
                        time.sleep(0.01)
                    assert observed, "Second request did not reach a database boundary"
                finally:
                    release.set()
                assert one.result(timeout=5).status_code == 200
                result = two.result(timeout=5)
                assert result.status_code == (
                    200 if second_action == "reassign" else 404
                ), result.text
        finally:
            release.set()
            event.remove(runtime, "after_cursor_execute", pause)
    db.expire_all()
    assert db.get(Company, c.id).manager_id == (
        last.id if second_action == "reassign" else new.id
    )
    assert list(db.scalars(select(Grant.staff_id).where(Grant.company_id == c.id))) == [
        last.id if second_action == "reassign" else new.id
    ]
    assert db.scalar(select(func.count()).select_from(Note)) == 0


def test_step_up_attempt_budget_is_durable_and_separate_from_login(
    client, staff_factory
):
    owner, target = staff_factory(), staff_factory("Manager")
    authenticate(client, owner)
    body = dict(role="Administrator", active=True, reason="Access review")
    for _ in range(12):
        assert (
            client.patch("/api/control/staff/" + target.id, json=body).status_code
            == 403
        )
    assert client.patch("/api/control/staff/" + target.id, json=body).status_code == 429
    assert client.get("/api/control/auth/me").status_code == 200
