"""Contract tests for explicit plan.parts vehicle/category/article reads. No paid calls."""
import httpx
from app.services.plan_parts import PlanPartsClient, RequestGate, provider_results


def test_documented_envelope_without_count_or_selectors():
    result = provider_results({"success": True, "data": {"results": [{"art_id": 10}]}}, {"ktype": 7, "pt_id": 3})
    assert result == [{"art_id": 10}]


def test_mismatched_echo_rejected():
    try:
        provider_results({"success": True, "data": {"ktype": 8, "results": []}}, {"ktype": 7})
        assert False, "Must reject different vehicle"
    except ValueError:
        pass


def test_live_catalog_contracts_with_mocked_transport(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "safe-test-key")
    events = []
    def handler(request):
        events.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/ktype"):
            payload = {"success": True, "data": {"results": [{"ktype": 1234, "brand": "VOLVO", "modification": "XC40 T3", "year_from": "2018-01", "power_kw": 120}]}}
        elif request.url.path.endswith("/categories"):
            payload = {"success": True, "data": {"results": [{"pt_id": 5, "name": "Brake pads", "article_count": 2}]}}
        else:
            payload = {"success": True, "data": {"results": [{"art_id": 10, "article_nr": "AA-123", "brand": "A", "part_name": "Brake pads"}, {"art_id": 11, "article_nr": "BB-123", "brand": "B", "part_name": "Brake pads"}]}}
        return httpx.Response(200, json=payload)
    client = PlanPartsClient(transport=httpx.MockTransport(handler))
    gate = RequestGate()
    result = client.vehicle_matches("owner", "Volvo", "XC40", 2018, gate=gate)
    assert result[0].ktype == 1234
    assert client.categories("owner", 1234, gate=gate)[0].article_count == 2
    rows = client.articles("owner", 1234, 5, gate=gate)
    assert len(rows) == 2
    assert len({r.part_name for r in rows}) == 1
    assert events[0][1] == {"brand": "Volvo", "model": "XC40", "year": "2018"}
    assert events[2][1] == {"ktype": "1234", "pt_id": "5"}
