"""Transient plan.parts cache contract: avoid repeat token spending on same lookup."""
import httpx
from app.services.plan_parts import PlanPartsClient, RequestGate, _result_cache


def test_repeated_categories_reuses_validated_cache(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "test-value")
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "data": {"results": [
            {"pt_id": 5, "name": "Brake disc", "article_count": 23}
        ]}})
    transport = httpx.MockTransport(provider)
    gate = RequestGate()
    client = PlanPartsClient(transport=transport)
    try:
        first = client.categories("owner-cache-test", 131094, gate)
        second = client.categories("owner-cache-test", 131094, gate)
        assert len(calls) == 1
        assert first[0].name == second[0].name
        assert first is not second
        assert first[0] is not second[0]
    finally:
        _result_cache.clear()


def test_cache_does_not_mix_workspaces_or_modifications(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "test-value")
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "data": {"results": [
            {"pt_id": 5, "name": "Brake disc", "article_count": 23}
        ]}})
    client = PlanPartsClient(transport=httpx.MockTransport(provider))
    try:
        client.categories("tenant-a", 131094, RequestGate())
        client.categories("tenant-b", 131094, RequestGate())
        client.categories("tenant-a", 131095, RequestGate())
        assert len(calls) == 3
    finally:
        _result_cache.clear()


def test_failures_not_cached(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "test-value")
    calls = []
    def provider(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500)
        return httpx.Response(200, json={"success": True, "data": {"results": [
            {"pt_id": 5, "name": "Brake disc", "article_count": 23}
        ]}})
    client = PlanPartsClient(transport=httpx.MockTransport(provider))
    from app.services.plan_parts import PlanPartsError
    try:
        try:
            client.categories("failed-first", 131094, RequestGate())
            assert False, "First request should fail"
        except PlanPartsError:
            pass
        result = client.categories("failed-first", 131094, RequestGate())
        assert len(result) == 1
        assert len(calls) == 2
    finally:
        _result_cache.clear()
