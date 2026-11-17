import pytest
from sqlalchemy import select, func
from app.control_center import config, security
from app.control_center.models import Audit, Session
from test_support import authenticate

PASSWORD = "long-staff-test-password"


def simplified(monkeypatch):
    monkeypatch.setenv("CONTROL_CENTER_AUTH_MODE", "password-only")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)


@pytest.mark.parametrize(
    "env,runtime,runtime_id,expected_id,allowed",
    [
        ("production", "production", "prod-id", "stage-id", False),
        ("production", "warehouse-staging", "stage-id", "stage-id", False),
        ("staging", "production", "prod-id", "stage-id", False),
        ("staging", "warehouse-staging", "prod-id", "stage-id", False),
        ("staging", "warehouse-staging", "stage-id", "", False),
        ("staging", "", "", "stage-id", False),
        ("staging", "warehouse-staging", "stage-id", "stage-id", True),
        ("local", "production", "prod-id", "stage-id", False),
        ("local", "", "", "", True),
    ],
)
def test_password_policy_is_bound_to_actual_runtime(
    monkeypatch, env, runtime, runtime_id, expected_id, allowed
):
    monkeypatch.setenv("CONTROL_CENTER_AUTH_MODE", "password-only")
    monkeypatch.setenv("CONTROL_CENTER_SOURCE_ENVIRONMENT", env)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", runtime)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", runtime_id)
    monkeypatch.setenv("CONTROL_CENTER_PASSWORD_ONLY_ENVIRONMENT_ID", expected_id)
    assert config.password_only() is allowed
    monkeypatch.setenv("CONTROL_CENTER_AUTH_MODE", "mfa")
    assert config.password_only() is False


def password_login(client, user, password=PASSWORD):
    r = client.post(
        "/api/control/auth/login",
        json={"username": user.username, "password": password},
    )
    if r.status_code == 200:
        client.headers["X-Control-CSRF"] = r.json()["csrf"]
    return r


def test_password_session_csrf_logout_and_policy_switch(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    user = staff_factory()
    assert client.get("/api/control/status").json()["auth_mode"] == "password-only"
    assert password_login(client, user).status_code == 200
    token = client.cookies.get(security.COOKIE)
    session = db.get(Session, security.digest(token))
    assert not session.mfa_verified
    assert session.audience == security.PASSWORD_AUDIENCE
    assert client.get("/api/control/readiness").status_code == 200
    assert client.get("/api/control/auth/csrf").json()["csrf"]
    assert (
        client.post(
            "/api/control/auth/logout", headers={"X-Control-CSRF": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.get(
            "/api/control/auth/csrf", headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    monkeypatch.setenv("CONTROL_CENTER_AUTH_MODE", "mfa")
    assert client.get("/api/control/auth/me").status_code == 401
    monkeypatch.setenv("CONTROL_CENTER_AUTH_MODE", "password-only")
    assert client.post("/api/control/auth/logout").status_code == 204
    client.cookies.set(security.COOKIE, token, path=security.COOKIE_PATH)
    assert client.get("/api/control/auth/me").status_code == 401


def test_password_login_remains_throttled_and_inactive_rejected(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    user = staff_factory()
    for _ in range(12):
        assert password_login(client, user, "wrong").status_code == 401
    assert password_login(client, user).status_code == 429
    other = staff_factory("Support")
    other.active = False
    db.commit()
    assert password_login(client, other).status_code == 401


def test_normal_password_change_revokes_all_sessions_no_mfa(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    user = staff_factory("Manager")
    assert password_login(client, user).status_code == 200
    first = client.cookies.get(security.COOKIE)
    assert password_login(client, user).status_code == 200
    body = {"current_password": PASSWORD, "new_password": "new-ordinary-password"}
    assert (
        client.post(
            "/api/control/auth/password", json=body, headers={"X-Control-CSRF": ""}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/control/auth/password", json={**body, "current_password": "wrong"}
        ).status_code
        == 422
    )
    assert client.post("/api/control/auth/password", json=body).status_code == 204
    assert client.get("/api/control/auth/me").status_code == 401
    assert db.get(Session, security.digest(first)) is None
    assert password_login(client, user).status_code == 401
    assert password_login(client, user, body["new_password"]).status_code == 200
    audit = db.scalars(select(Audit).where(Audit.permission == "auth.password")).all()
    assert {a.result for a in audit} == {"success", "denied"}
    assert all(not a.safe_diff for a in audit)


def test_default_mfa_still_required_for_login_and_password_change(
    client, staff_factory
):
    user = staff_factory()
    assert password_login(client, user).status_code == 401
    authenticate(client, user)
    assert (
        client.post(
            "/api/control/auth/password",
            json={
                "current_password": PASSWORD,
                "new_password": "another-safe-password",
            },
        ).status_code
        == 403
    )


def test_retirement_invalidates_pending_enrollment_and_is_idempotent(
    client, staff_factory, db, monkeypatch
):
    owner = staff_factory()
    original_seed = owner.mfa_ciphertext
    authenticate(client, owner)
    enroll = client.post("/api/control/auth/enrollment").json()
    assert "enrollment" in enroll
    simplified(monkeypatch)
    assert security.retire_staging_owner_mfa() == 1
    assert security.retire_staging_owner_mfa() == 0
    db.refresh(owner)
    assert owner.mfa_ciphertext != original_seed
    assert client.get("/api/control/auth/me").status_code == 401
    assert password_login(client, owner).status_code == 200
    assert client.post("/api/control/auth/enrollment").status_code == 409
    payload = {k: v for k, v in enroll.items() if k == "enrollment"}
    assert (
        client.post(
            "/api/control/auth/rotate",
            json={
                "current_password": PASSWORD,
                "new_password": "new-valid-password",
                "current_code": "000000",
                "new_code": "000000",
                **payload,
            },
        ).status_code
        == 409
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Audit)
            .where(Audit.permission == "auth.mfa_retired")
        )
        == 1
    )


def test_password_only_keeps_scope_and_stepup(client, staff_factory, db, monkeypatch):
    from test_security import company

    simplified(monkeypatch)
    owner, manager = staff_factory(), staff_factory("Manager")
    company(db)
    assert password_login(client, manager).status_code == 200
    assert client.get("/api/control/companies").json()["items"] == []
    assert password_login(client, owner).status_code == 200
    body = {
        "role": "Support",
        "active": True,
        "finance": False,
        "reason": "scope cleanup",
    }
    assert (
        client.patch("/api/control/staff/" + manager.id, json=body).status_code == 403
    )
    assert (
        client.patch(
            "/api/control/staff/" + manager.id,
            json={**body, "current_password": PASSWORD},
        ).status_code
        == 200
    )


def test_retirement_preserves_company_work_history_and_is_disabled_with_mfa(
    db, staff_factory, monkeypatch
):
    from app.control_center.models import Company, SourceLink, Grant, Note, Task
    from test_security import company

    owner = staff_factory()
    row = company(db)
    db.add_all(
        [
            Grant(company_id=row.id, staff_id=owner.id),
            Note(
                company_id=row.id, staff_id=owner.id, text="retained internal history"
            ),
            Task(company_id=row.id, assignee_id=owner.id, next_action="retained task"),
            SourceLink(
                company_id=row.id,
                system="warehouse",
                environment="local",
                entity_type="workspace",
                source_id="stable-source",
                status="verified",
            ),
        ]
    )
    db.commit()
    tables = [Company, SourceLink, Grant, Note, Task]

    def counts():
        return [db.scalar(select(func.count()).select_from(t)) for t in tables]

    before = counts()
    ciphertext = owner.mfa_ciphertext
    assert security.retire_staging_owner_mfa() == 0
    db.refresh(owner)
    assert owner.mfa_ciphertext == ciphertext
    simplified(monkeypatch)
    assert security.retire_staging_owner_mfa() == 1
    assert counts() == before
    assert db.scalar(select(Note.text)) == "retained internal history"
