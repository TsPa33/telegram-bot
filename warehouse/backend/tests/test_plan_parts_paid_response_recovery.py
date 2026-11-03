"""Paid response recovery tests use local HTTP mocks; zero real supplier tokens."""
import httpx
import pytest
from app.services.plan_parts import (
    PlanPartsClient, PlanPartsError, RequestGate, _raw_response_cache, _result_cache,
    provider_results,
)


def test_provider_count_can_represent_total_count():
    data=provider_results(
        {"success":True,"data":{"count":70,"limit":50,"results":[
            {"art_id":1,"article_nr":"A","brand":"B","part_name":"C"}]}},
        {"ktype":131094,"pt_id":444})
    assert len(data)==1


def test_cache_only_recovery_never_calls_supplier(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED","true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY","safe-test-key")
    count=[0]
    bad={"success":True,"data":{"results":[{"art_id":1,"article_nr":"A",
                                              "brand":"B","part_name":None}]}}
    def fake(request):
        count[0]+=1
        return httpx.Response(200,json=bad)
    client=PlanPartsClient(transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(PlanPartsError) as exc:
            client.articles("tenant-recover",131094,333,gate=RequestGate())
        assert exc.value.status==502
        assert count[0]==1
        with pytest.raises(PlanPartsError) as exc:
            client.recover_articles("tenant-recover",131094,333)
        assert exc.value.status==502
        assert count[0]==1
        bad["data"]["results"][0]["part_name"]="Repair kit"
        # Re-test payload parsing by updating in-memory fixture to emulate a
        # corrected vendor response already stored in the raw cache.
        import json
        with __import__("app.services.plan_parts",fromlist=["_cache_lock"])._cache_lock:
            key=next(k for k in _raw_response_cache if k[0]=="tenant-recover")
            expiry,_=_raw_response_cache[key]
            _raw_response_cache[key]=(expiry,json.dumps(bad).encode())
        rows=client.recover_articles("tenant-recover",131094,333)
        assert len(rows)==1 and rows[0].part_name=="Repair kit"
        assert count[0]==1
    finally:
        _raw_response_cache.clear()
        _result_cache.clear()


def test_absent_raw_cache_never_calls_provider(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED","true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY","safe-test-key")
    def forbidden(request):
        raise AssertionError("No paid outbound request allowed")
    client=PlanPartsClient(transport=httpx.MockTransport(forbidden))
    try:
        with pytest.raises(PlanPartsError) as exc:
            client.recover_articles("unseen-tenant",131094,10)
        assert exc.value.status==409
    finally:
        _raw_response_cache.clear()
        _result_cache.clear()
