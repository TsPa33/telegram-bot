"""Realistic plan.parts articles can contain missing or null names; never bill again to parse."""
import httpx
from app.services.plan_parts import PlanPartsClient, RequestGate, _result_cache, _raw_response_cache


def test_articles_allow_null_and_omitted_part_name(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "test-secret")
    seen = []
    def provider(request):
        seen.append(request)
        return httpx.Response(200, json={"success": True, "data": {"results": [
            {"art_id": 10, "article_nr": "A10", "brand": "BRAND", "part_name": None},
            {"art_id": 11, "article_nr": "A11", "brand": "BRAND"},
            {"art_id": 12, "article_nr": "A12", "brand": "BRAND", "part_name": "Brake pad"}
        ]}})
    client = PlanPartsClient(transport=httpx.MockTransport(provider))
    try:
        rows = client.articles("owner-null-name-case", 131094, 7777, RequestGate())
        assert [row.part_name for row in rows] == ["", "", "Brake pad"]
        again = client.articles("owner-null-name-case", 131094, 7777, RequestGate())
        assert len(again) == 3
        assert len(seen) == 1
    finally:
        _result_cache.clear()
        _raw_response_cache.clear()
