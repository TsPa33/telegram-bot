import httpx
import pytest

from app.services.plan_parts import Modification, PlanPartsClient, PlanPartsError, RequestGate, modifications_for_year


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "offline-placeholder-not-a-real-key")


@pytest.mark.parametrize("resource,selector", [("models", "mfa_id=121"), ("modifications", "ms_id=1994")])
def test_confirmed_query_parameters(resource, selector):
    def handler(request):
        assert request.url.path == f"/api/v1/aftermarket/catalog/{resource}"
        assert request.url.query.decode() == selector
        return httpx.Response(200, json=[])
    client = PlanPartsClient(httpx.MockTransport(handler))
    assert getattr(client, resource)("account-a", int(selector.split("=")[1]), RequestGate()) == []


def test_models_use_confirmed_name_field_and_explicit_override(monkeypatch):
    client = PlanPartsClient(httpx.MockTransport(lambda request: httpx.Response(200, json=[{"ms_id":1994,"test_label":"Golf IV (1J1)","name":"not-confirmed"}])))
    monkeypatch.delenv("PLAN_PARTS_MODEL_NAME_FIELD", raising=False)
    assert client.models("a", 121, RequestGate())[0].name == "not-confirmed"
    monkeypatch.setenv("PLAN_PARTS_MODEL_NAME_FIELD", "test_label")
    assert client.models("a", 121, RequestGate())[0].name == "Golf IV (1J1)"
    monkeypatch.setenv("PLAN_PARTS_MODEL_NAME_FIELD", "absent")
    with pytest.raises(PlanPartsError):
        client.models("a", 121, RequestGate())


@pytest.mark.parametrize("value,expected", [(1997,1997),("1997",1997),("1997-08",1997),("1997-08-01",1997),(None,None)])
def test_supported_year_formats(value, expected):
    assert Modification(ktype=16063, modification="1.9 TDI", year_from=value).year_from == expected


@pytest.mark.parametrize("value", [True,"1997/08","1997-13","unknown",0])
def test_unsupported_year_formats_fail_closed(value):
    with pytest.raises(ValueError):
        Modification(ktype=16063, modification="1.9 TDI", year_from=value)


def test_inclusive_year_filter_and_ambiguity():
    records = [Modification(ktype=1,modification="A",year_from=1997,year_to=2003),
               Modification(ktype=2,modification="B",year_from=2000,year_to=None),
               Modification(ktype=3,modification="C",year_from=None,year_to=None)]
    assert [m.ktype for m in modifications_for_year(records, 2000)] == [1,2]
    assert [m.ktype for m in modifications_for_year(records, 2003)] == [1,2]
    assert [m.ktype for m in modifications_for_year(records, 2004)] == [2]
    assert modifications_for_year(records, 1996) == []
    assert modifications_for_year(records, None) == records


def test_one_workflow_not_blocked_but_duplicate_is():
    gate = RequestGate()
    for operation in ("brands", "models121", "modifications1994"):
        gate.acquire("account-a", operation)
    with pytest.raises(PlanPartsError):
        gate.acquire("account-a", "models121")
    gate.acquire("account-b", "models121")


def test_routes_validate_selectors_and_filter_without_auto_selecting():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.plan_parts import router, plan_parts_client
    from app.api.deps import identity
    app = FastAPI()
    app.include_router(router)
    calls = []
    class Client:
        def models(self, account, selector):
            calls.append((account, selector))
            return []
        def modifications(self, account, selector):
            calls.append((account, selector))
            return [Modification(ktype=i, modification="TDI",year_from=1997,year_to=2004) for i in (16063,16064)]
    app.dependency_overrides[identity] = lambda: SimpleNamespace(user=SimpleNamespace(id="account-a"))
    app.dependency_overrides[plan_parts_client] = lambda: Client()
    with TestClient(app) as client:
        assert client.post("/api/v1/plan-parts/models/lookup?mfa_id=0").status_code == 422
        assert client.post("/api/v1/plan-parts/models/lookup?mfa_id=121").json() == []
        response = client.post("/api/v1/plan-parts/modifications/lookup?ms_id=1994&year=2001")
        assert response.status_code == 200
        assert [row["ktype"] for row in response.json()] == [16063,16064]
        assert client.post("/api/v1/plan-parts/modifications/lookup?ms_id=1994&year=1800").status_code == 422
    assert calls == [("account-a",121),("account-a",1994)]


def test_concurrent_duplicate_lookup_is_suppressed():
    from concurrent.futures import ThreadPoolExecutor
    gate = RequestGate()
    def attempt(_):
        try:
            gate.acquire("same-account", "models121")
            return True
        except PlanPartsError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(32))) == 1


def test_account_and_global_attempt_budgets():
    gate = RequestGate()
    for index in range(10):
        gate.acquire("account-a", str(index))
    with pytest.raises(PlanPartsError):
        gate.acquire("account-a", "eleventh")
    gate = RequestGate()
    for index in range(60):
        gate.acquire(str(index), "brands")
    with pytest.raises(PlanPartsError):
        gate.acquire("another-account", "brands")


@pytest.mark.parametrize("path", ["brands/lookup", "models/lookup?mfa_id=121", "modifications/lookup?ms_id=1994"])
def test_staging_rejects_wrong_origin_before_provider_call(monkeypatch, path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import get_db
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_PUBLIC_ORIGIN", "https://warehouse.example.test")
    def forbidden_db():
        pytest.fail("Rejected Origin must not reach authentication or provider")
    app.dependency_overrides[get_db] = forbidden_db
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/plan-parts/" + path, headers={"Origin":"https://wrong.example.test"})
            assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
