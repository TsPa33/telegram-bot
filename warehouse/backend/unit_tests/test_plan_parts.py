"""Offline tests: no database, provider credentials or network required."""

from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.plan_parts import plan_parts_client, router
from app.db import get_db
from app.models import Account, Session, now
from app.services.auth import digest
from app.services.plan_parts import MAX_RESPONSE_BYTES, PlanPartsClient, PlanPartsError, RequestGate


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "offline-placeholder-not-a-real-key")


def run(handler, account="a", gate=None):
    return PlanPartsClient(httpx.MockTransport(handler)).brands(account, gate or RequestGate())


def test_brands_contract_and_auth():
    def handler(request):
        assert str(request.url) == "https://cdn.plan.parts/api/v1/aftermarket/catalog/brands"
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer offline-placeholder-not-a-real-key"
        return httpx.Response(200, json=[{"brand": "Volkswagen", "mfa_id": 121}])
    result = run(handler)
    assert result[0].model_dump() == {"brand": "Volkswagen", "mfa_id": 121}


@pytest.mark.parametrize("payload", [[], [{"brand": "A", "mfa_id": 1}, {"brand": "A", "mfa_id": 2}]])
def test_empty_and_identical_names(payload):
    assert len(run(lambda request: httpx.Response(200, json=payload))) == len(payload)


@pytest.mark.parametrize("payload", [
    {"data": []}, {"success": True, "data": {"results": []}},
    {"success": True, "data": []}, {"success": False, "data": {"results": []}},
    [{"brand": "A"}], [{"brand": "", "mfa_id": 1}],
    [{"brand": "A", "mfa_id": True}], [{"brand": "A", "mfa_id": "121"}],
    [{"brand": "A", "mfa_id": 1}, {"brand": "B", "mfa_id": 1}],
])
def test_reject_unconfirmed_or_invalid_formats(payload):
    with pytest.raises(PlanPartsError) as exc:
        run(lambda request: httpx.Response(200, json=payload))
    assert exc.value.status == 502


@pytest.mark.parametrize("status,expected", [(401,502),(403,502),(429,429),(500,502),(302,502)])
def test_provider_errors_are_sanitized_without_retry(status, expected, caplog):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive-provider-body", headers={"Location": "https://example.test"})
    with pytest.raises(PlanPartsError) as exc:
        run(handler)
    assert exc.value.status == expected
    assert len(calls) == 1
    assert "sensitive-provider-body" not in str(exc.value) + caplog.text
    assert "offline-placeholder-not-a-real-key" not in str(exc.value) + caplog.text


@pytest.mark.parametrize("error,status", [(httpx.ReadTimeout,504),(httpx.ConnectError,502)])
def test_network_errors(error, status):
    def handler(request):
        raise error("sensitive-provider-body", request=request)
    with pytest.raises(PlanPartsError) as exc:
        run(handler)
    assert exc.value.status == status
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize("body", [b"invalid json", b"x" * (MAX_RESPONSE_BYTES + 1)])
def test_invalid_or_oversized_body(body):
    with pytest.raises(PlanPartsError) as exc:
        run(lambda request: httpx.Response(200, content=body))
    assert exc.value.status == 502


@pytest.mark.parametrize("variable,value", [("PLAN_PARTS_ENABLED","false"),("PLAN_PARTS_API_KEY","")])
def test_disabled_or_missing_key_never_calls_provider(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    def forbidden(request):
        pytest.fail("Unexpected provider request")
    with pytest.raises(PlanPartsError) as exc:
        run(forbidden)
    assert exc.value.status == 503


def test_attempt_budget_is_account_scoped_and_expires():
    clock = [100.0]
    gate = RequestGate(clock=lambda: clock[0])
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[])
    run(handler, "a", gate)
    with pytest.raises(PlanPartsError):
        run(handler, "a", gate)
    clock[0] += 2
    run(handler, "b", gate)
    with pytest.raises(PlanPartsError):
        run(handler, "a", gate)
    clock[0] += 60
    run(handler, "a", gate)
    assert len(calls) == 3


def test_failed_requests_consume_budget():
    gate = RequestGate()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(500)
    for expected in (502, 429):
        with pytest.raises(PlanPartsError) as exc:
            run(handler, gate=gate)
        assert exc.value.status == expected
    assert len(calls) == 1


def test_router_registered_in_warehouse_without_database_or_network():
    from app.main import app
    # A non-session request never opens a DB session when dependency is stubbed.
    app.dependency_overrides[get_db] = lambda: None
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/plan-parts/brands/lookup")
            assert response.status_code == 401
            assert response.headers["Cache-Control"] == "no-store"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize("path", [
    "/api/v1/plan-parts/brands/lookup",
    "/api/v1/plan-parts/models/lookup?mfa_id=121",
    "/api/v1/plan-parts/modifications/lookup?ms_id=1994",
])
def test_route_requires_session_csrf_and_uses_authenticated_account(path):
    app = FastAPI()
    app.include_router(router)
    account = Account(id="account-a", role="DIRECTOR", workspace_account_id=None,
                      permissions=[], is_active=True, must_change_password=False)
    session = SimpleNamespace(expires_at=now()+timedelta(hours=1), account_id=account.id, csrf_hash=digest("csrf"))
    class DB:
        def __init__(self):
            self.info = {}

        def get(self, model, key):
            return session if model is Session else account
    calls = []
    class Client:
        def brands(self, account_id):
            calls.append(account_id)
            return []
        def models(self, account_id, selector):
            return self.brands(account_id)
        def modifications(self, account_id, selector):
            return self.brands(account_id)
    app.dependency_overrides[get_db] = lambda: DB()
    app.dependency_overrides[plan_parts_client] = lambda: Client()
    with TestClient(app) as client:
        assert calls == []
        assert client.get(path).status_code == 405
        assert client.post(path).status_code == 401
        client.cookies.set("warehouse_session", "session-placeholder")
        assert client.post(path).status_code == 403
        assert calls == []
        assert client.post(path, headers={"X-CSRF-Token":"csrf"}).status_code == 200
        assert calls == ["account-a"]
        account.is_active = False
        assert client.post(path, headers={"X-CSRF-Token":"csrf"}).status_code == 401
        account.is_active = True
        account.must_change_password = True
        assert client.post(path, headers={"X-CSRF-Token":"csrf"}).status_code == 403
        assert calls == ["account-a"]
