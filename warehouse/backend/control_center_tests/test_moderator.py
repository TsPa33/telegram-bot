"""Least-privilege staff accounts, real PostgreSQL and runtime role."""

from datetime import timedelta
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.control_center.models import Staff, Session, Audit, Task, Note, now
from app.control_center import security as sec
from test_support import authenticate, SECRET
from test_security import company
from test_password_policy import simplified, password_login, PASSWORD


def command(**extra):
    return dict(current_password=PASSWORD, reason="Approved staff access", **extra)


def create(client, username="new.moderator"):
    response = client.post("/api/control/staff", json=command(username=username))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("role", ["Moderator", "Manager", "Support", "Administrator"])
def test_non_owner_cannot_provision_reset_or_mutate(client, staff_factory, role):
    user, owner = staff_factory(role), staff_factory()
    authenticate(client, user)
    assert (
        client.post("/api/control/staff", json=command(username="someone")).status_code
        == 403
    )
    assert (
        client.post(f"/api/control/staff/{owner.id}/reset", json=command()).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/control/staff/{user.id}",
            json=command(role="Owner", active=True, finance=True),
        ).status_code
        == 403
    )
    assert client.get("/api/control/audit").status_code == 403
    if role != "Administrator":
        assert client.get("/api/control/staff").status_code == 403


def test_moderator_all_contacts_notes_and_tasks_but_no_admin(client, staff_factory, db):
    moderator = staff_factory("Moderator", finance=True)
    other = staff_factory("Manager")
    a, b, foreign = (
        company(db, workspace="a"),
        company(db, workspace="b"),
        company(db, workspace="c", env="production"),
    )
    for row in (a, b):
        row.snapshot = {**row.snapshot, "source_environment": "local"}
    task = Task(company_id=b.id, assignee_id=other.id, next_action="Review")
    note = Note(company_id=a.id, staff_id=other.id, text="existing")
    foreign_task = Task(
        company_id=foreign.id, assignee_id=other.id, next_action="Secret"
    )
    db.add_all([task, note, foreign_task])
    db.commit()
    authenticate(client, moderator)
    me = client.get("/api/control/auth/me").json()
    assert me["can_finance"] is False and me["can_assign"] is False
    assert {x["id"] for x in client.get("/api/control/companies").json()["items"]} == {
        a.id,
        b.id,
    }
    for row in (a, b):
        assert (
            client.get(f"/api/control/companies/{row.id}").json()["people"][0]["email"]
            == "owner@private.test"
        )
        assert client.get(f"/api/control/companies/{row.id}/finance").status_code == 403
        assert (
            client.post(
                f"/api/control/companies/{row.id}/notes",
                json={"text": "moderator note"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/control/companies/{row.id}/tasks",
                json={"next_action": "My task"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/control/companies/{row.id}/assign", json={"staff_id": other.id}
            ).status_code
            == 403
        )
    assert (
        client.patch(
            f"/api/control/companies/{a.id}/notes/{note.id}", json={"text": "updated"}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/control/tasks/{task.id}",
            json={"next_action": "Done", "status": "done"},
        ).status_code
        == 200
    )
    assert foreign_task.id not in {
        x["id"] for x in client.get("/api/control/tasks").json()
    }
    for suffix in ("", "/notes", "/finance"):
        assert (
            client.get(f"/api/control/companies/{foreign.id}{suffix}").status_code
            == 404
        )
    assert (
        client.patch(
            f"/api/control/tasks/{foreign_task.id}", json={"next_action": "attack"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/control/companies/{a.id}/notes",
            json={"text": "csrf"},
            headers={"X-Control-CSRF": "bad"},
        ).status_code
        == 403
    )


def test_owner_create_canonical_single_use_and_forced_rotation(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    owner = staff_factory()
    password_login(client, owner)
    assert (
        client.post(
            "/api/control/staff", json={"username": "new.person", "reason": "test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/control/staff",
            json=command(username="new.person"),
            headers={"X-Control-CSRF": "bad"},
        ).status_code
        == 403
    )
    result = create(client, "New.Person")
    staff_id, password = result["staff"]["id"], result["temporary_password"]
    assert result["staff"]["username"] == "new.person"
    assert (
        client.post(
            "/api/control/staff", json=command(username="NEW.PERSON")
        ).status_code
        == 409
    )
    assert "temporary_password" not in client.get("/api/control/staff").text
    with TestClient(
        client.app,
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    ) as member:
        user = db.get(Staff, staff_id)
        assert password_login(member, user, password).status_code == 200
        assert (
            password_login(member, user, password).status_code == 401
        )  # consumed, existing session remains
        assert member.get("/api/control/companies").status_code == 403
        assert member.get("/api/control/tasks").status_code == 403
        assert member.get("/api/control/auth/me").json()["must_change_password"]
        proof = member.get("/api/control/auth/csrf").json()["csrf"]
        member.headers["X-Control-CSRF"] = proof
        body = dict(
            current_password=password, new_password="new-personal-secure-password"
        )
        assert member.post("/api/control/auth/password", json=body).status_code == 204
        assert member.get("/api/control/auth/me").status_code == 401
        assert password_login(member, user, body["new_password"]).status_code == 200
        assert member.get("/api/control/companies").status_code == 200
    db.expire_all()
    user = db.get(Staff, staff_id)
    assert not user.must_change_password and user.temporary_expires_at is None
    assert password not in user.password_hash
    audits = list(db.scalars(select(Audit)))
    assert password not in str([(a.safe_diff, a.reason) for a in audits])


def test_disable_reactivate_reset_revokes_sessions(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    owner, moderator = staff_factory(), staff_factory("Moderator")
    password_login(client, owner)
    with TestClient(
        client.app,
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    ) as member:
        password_login(member, moderator)
        copied = member.cookies.get(sec.COOKIE)
        update = command(role="Moderator", active=False, finance=True)
        path = f"/api/control/staff/{moderator.id}"
        assert client.patch(path, json=update).status_code == 200
        assert member.get("/api/control/auth/me").status_code == 401
        assert password_login(member, moderator).status_code == 401
        assert client.patch(path, json={**update, "active": True}).status_code == 200
        assert password_login(member, moderator).status_code == 200
        reset = client.post(path + "/reset", json=command()).json()
        assert member.get("/api/control/auth/me").status_code == 401
        assert password_login(member, moderator).status_code == 401
        assert (
            password_login(member, moderator, reset["temporary_password"]).status_code
            == 200
        )
        assert member.get("/api/control/companies").status_code == 403
        db.expire_all()
        assert db.get(Session, sec.digest(copied)) is None
        assert not db.get(Staff, moderator.id).finance


def test_expired_temporary_access_and_expired_activation_session(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    owner = staff_factory()
    password_login(client, owner)
    result = create(client)
    target = db.get(Staff, result["staff"]["id"])
    target.temporary_expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert (
        password_login(client, target, result["temporary_password"]).status_code == 401
    )
    target.temporary_expires_at = now() + timedelta(hours=1)
    db.commit()
    assert (
        password_login(client, target, result["temporary_password"]).status_code == 200
    )
    session = db.get(Session, sec.digest(client.cookies.get(sec.COOKIE)))
    session.expires_at = now() - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            "/api/control/auth/password",
            json=dict(
                current_password=result["temporary_password"],
                new_password="a-new-personal-password",
            ),
        ).status_code
        == 401
    )


def test_mfa_activation_requires_session_bound_enrollment_and_keeps_mfa(
    client, staff_factory, db
):
    owner = staff_factory()
    authenticate(client, owner)
    code = sec.totp(SECRET, int(time.time()) // 30 + 1)
    body = dict(username="mfa.person", reason="Approved MFA access", mfa_code=code)
    result = client.post("/api/control/staff", json=body)
    assert result.status_code == 201, result.text
    assert (
        client.post(
            "/api/control/staff", json={**body, "username": "replayed"}
        ).status_code
        == 403
    )
    result = result.json()
    user = db.get(Staff, result["staff"]["id"])
    assert password_login(client, user, result["temporary_password"]).status_code == 200
    session = db.get(Session, sec.digest(client.cookies.get(sec.COOKIE)))
    assert not session.mfa_verified
    assert client.get("/api/control/companies").status_code == 403
    enroll = client.post("/api/control/auth/activation-enrollment").json()
    change = dict(
        current_password=result["temporary_password"],
        new_password="new-mfa-personal-password",
    )
    assert client.post("/api/control/auth/password", json=change).status_code == 422
    assert (
        client.post(
            "/api/control/auth/password",
            json={**change, "enrollment": enroll["enrollment"], "mfa_code": "000000"},
        ).status_code
        == 422
    )
    import json
    from app.control_center.config import cipher

    mismatched = json.loads(cipher().decrypt(enroll["enrollment"].encode()))
    mismatched["session"] = "another-session"
    invalid_enrollment = cipher().encrypt(json.dumps(mismatched).encode()).decode()
    assert (
        client.post(
            "/api/control/auth/password",
            json={
                **change,
                "enrollment": invalid_enrollment,
                "mfa_code": sec.totp(enroll["seed"], int(time.time()) // 30),
            },
        ).status_code
        == 422
    )
    step = int(time.time()) // 30
    assert (
        client.post(
            "/api/control/auth/password",
            json={
                **change,
                "enrollment": enroll["enrollment"],
                "mfa_code": sec.totp(enroll["seed"], step),
            },
        ).status_code
        == 204
    )
    assert password_login(client, user, change["new_password"]).status_code == 401
    response = client.post(
        "/api/control/auth/login",
        json=dict(
            username=user.username,
            password=change["new_password"],
            code=sec.totp(enroll["seed"], step + 1),
        ),
    )
    assert response.status_code == 200
    assert client.get("/api/control/companies").status_code == 200


def test_additive_upgrade_preserves_accounts_sessions_history(
    db, staff_factory, monkeypatch
):
    from pathlib import Path
    from app.control_center.manage import migrate

    # Reconstruct the actual pre-upgrade schema rather than testing only a fresh 002.
    with db.bind.begin() as c:
        c.execute(text("DROP SCHEMA control_center CASCADE"))
        c.connection.driver_connection.execute(
            (
                Path(__file__).parents[1] / "control_center_migrations/001.sql"
            ).read_text()
        )
        c.execute(
            text("INSERT INTO control_center.schema_version VALUES ('001','local')")
        )
        c.execute(
            text(
                "INSERT INTO control_center.staff VALUES ('stable-id','legacy','hash','cipher',-1,'Manager',false,true,now())"
            )
        )
        c.execute(
            text(
                "INSERT INTO control_center.sessions VALUES ('token','stable-id','csrf','carpot-control-center',true,now()+interval '1 hour')"
            )
        )
        c.execute(
            text(
                "INSERT INTO control_center.audit VALUES ('audit','stable-id','test','staff','stable-id','request',null,'{}','success',now())"
            )
        )
    import os

    monkeypatch.setenv(
        "CONTROL_CENTER_MIGRATOR_URL", os.environ["CONTROL_CENTER_TEST_ADMIN_URL"]
    )
    migrate()
    migrate()
    with db.bind.connect() as c:
        assert c.scalar(text("SELECT id FROM control_center.staff")) == "stable-id"
        assert (
            c.scalar(text("SELECT token_hash FROM control_center.sessions")) == "token"
        )
        assert c.scalar(text("SELECT id FROM control_center.audit")) == "audit"
        assert (
            c.scalar(text("SELECT must_change_password FROM control_center.staff"))
            is False
        )


def test_account_create_and_reset_are_atomic_with_audit(
    client, staff_factory, db, monkeypatch
):
    simplified(monkeypatch)
    owner, member = staff_factory(), staff_factory("Moderator")
    password_login(client, member)
    copied = client.cookies.get(sec.COOKIE)
    password_login(client, owner)
    with db.bind.begin() as c:
        c.execute(text("REVOKE INSERT ON control_center.audit FROM cc_app"))
    assert (
        client.post(
            "/api/control/staff", json=command(username="rollback.person")
        ).status_code
        == 503
    )
    assert (
        client.post(f"/api/control/staff/{member.id}/reset", json=command()).status_code
        == 503
    )
    db.expire_all()
    assert db.scalar(select(Staff).where(Staff.username == "rollback.person")) is None
    assert not db.get(Staff, member.id).must_change_password
    assert db.get(Session, sec.digest(copied)) is not None


def test_temporary_password_is_single_use_under_concurrent_login(
    client, staff_factory, db, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    simplified(monkeypatch)
    password_login(client, staff_factory())
    created = create(client)

    def attempt():
        with TestClient(
            client.app,
            base_url="http://testserver",
            headers={"Origin": "http://testserver"},
        ) as other:
            return other.post(
                "/api/control/auth/login",
                json=dict(
                    username=created["staff"]["username"],
                    password=created["temporary_password"],
                ),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == [200, 401]


def test_moderator_contact_evidence_and_scoped_note_edit_guards(
    client, staff_factory, db
):
    moderator, manager = staff_factory("Moderator"), staff_factory("Manager")
    a, b = company(db, workspace="a"), company(db, workspace="b")
    a.snapshot = {**a.snapshot, "source_environment": "production"}
    b.snapshot = {**b.snapshot, "source_environment": "local"}
    b.labels = ["Демонстрація"]
    note = Note(company_id=b.id, staff_id=moderator.id, text="context bound")
    db.add(note)
    db.commit()
    authenticate(client, moderator)
    for row in (a, b):
        assert (
            client.get(f"/api/control/companies/{row.id}").json()["people"][0]["email"]
            == "o***@private.test"
        )
    assert (
        client.patch(
            f"/api/control/companies/{a.id}/notes/{note.id}",
            json={"text": "cross company"},
        ).status_code
        == 404
    )
