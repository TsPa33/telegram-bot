"""User-provided real exports, replayed offline; no API key or DB needed."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from app.services.plan_parts import (
    CatalogPartType, PlanPartsClient, PlanPartsError, RequestGate,
    modifications_for_year, provider_results,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
FILES = {
    "brands": "plan_parts_brands_708.json",
    "models": "plan_parts_models_vw_121_292.json",
    "modifications": "plan_parts_modifications_golf4_1994_35.json",
    "categories": "plan_parts_categories_volvo_9743_632.json",
}


def fixture(resource):
    return json.loads((FIXTURES / FILES[resource]).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def offline_configuration(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "offline-placeholder-not-a-real-key")
    monkeypatch.delenv("PLAN_PARTS_MODEL_NAME_FIELD", raising=False)


@pytest.mark.parametrize("resource,selector,count", [("brands",None,708),("models",121,292),("modifications",1994,35)])
def test_client_replays_real_exports(resource, selector, count):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/api/v1/aftermarket/catalog/" + resource
        assert dict(request.url.params) == ({} if selector is None else {"mfa_id" if resource == "models" else "ms_id":str(selector)})
        return httpx.Response(200, json=fixture(resource))
    client = PlanPartsClient(httpx.MockTransport(handler))
    args = ("offline-account",) if selector is None else ("offline-account",selector)
    rows = getattr(client,resource)(*args,gate=RequestGate())
    assert len(rows) == count
    assert len(calls) == 1
    if resource == "brands":
        assert any(row.mfa_id == 121 and row.brand == "VW" for row in rows)
    if resource == "models":
        golf = next(row for row in rows if row.ms_id == 1994)
        assert (golf.name,golf.year_from,golf.year_to) == ("GOLF IV (1J1)",1997,2008)
        assert sum(row.year_to is None for row in rows) == 76
    if resource == "modifications":
        tdi = next(row for row in rows if row.ktype == 16063)
        assert (tdi.modification,tdi.displacement_cc,tdi.power_kw,tdi.power_ps) == ("1.9 TDI",1896,96,130)
        assert (tdi.year_from,tdi.year_to) == (2000,2005)
        assert tdi in modifications_for_year(rows,2000)
        assert tdi in modifications_for_year(rows,2005)
        assert tdi not in modifications_for_year(rows,1999)
        assert tdi not in modifications_for_year(rows,2006)
        assert len(modifications_for_year(rows,2001)) > 1


def test_categories_export_is_catalog_not_inventory():
    payload = fixture("categories")
    rows = [CatalogPartType.model_validate(row) for row in provider_results(payload,{"ktype":9743})]
    assert len(rows) == 632
    assert len({row.pt_id for row in rows}) == 632
    assert all("quantity" not in row.model_dump() for row in rows)
    assert next(row for row in rows if row.pt_id == 3908).article_count == 4


@pytest.mark.parametrize("mutation", ["failure","count","selector","row_selector","limit","truncation"])
def test_corrupted_real_envelope_fails_closed(mutation):
    payload = copy.deepcopy(fixture("models"))
    if mutation == "failure": payload["success"] = False
    if mutation == "count": payload["data"]["count"] = True
    if mutation == "selector": payload["data"]["mfa_id"] = 999
    if mutation == "row_selector": payload["data"]["results"][0]["mfa_id"] = 999
    if mutation == "limit": payload["data"]["limit"] = 1
    if mutation == "truncation": payload["data"]["results"].pop()
    client = PlanPartsClient(httpx.MockTransport(lambda request: httpx.Response(200,json=payload)))
    with pytest.raises(PlanPartsError) as exc:
        client.models("offline-account",121,RequestGate())
    assert exc.value.status == 502
