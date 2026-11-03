"""No-charge restoration of plan.parts categories after a browser refresh."""
import httpx
import pytest
from app.services.plan_parts import (
    PlanPartsClient, PlanPartsError, RequestGate, _raw_response_cache, _result_cache
)


def test_category_recovery_uses_cache_not_provider(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "safe-mock-key")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"success": True, "data": {"results": [
            {"pt_id": 1, "name": "Accessory Kit, disc brake pad", "article_count": 70}
        ]}})
    transport=httpx.MockTransport(handler)
    client=PlanPartsClient(transport=transport)
    try:
        original=client.categories("owner-recovery", 131094, RequestGate())
        restored=client.recover_categories("owner-recovery", 131094)
        assert len(calls)==1
        assert restored[0].pt_id==original[0].pt_id
        assert restored[0].name==original[0].name
        assert restored is not original
    finally:
        _result_cache.clear()
        _raw_response_cache.clear()


def test_category_recovery_with_no_cache_does_not_call_provider(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "safe-mock-key")
    def forbidden(request):
        raise AssertionError("Must not spend tokens")
    client=PlanPartsClient(transport=httpx.MockTransport(forbidden))
    try:
        with pytest.raises(PlanPartsError) as exc:
            client.recover_categories("no-cached-categories", 131094)
        assert exc.value.status==409
    finally:
        _result_cache.clear()
        _raw_response_cache.clear()
