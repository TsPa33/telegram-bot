"""VINState diagnostic contract tests. No live HTTP and no paid VIN calls."""
import json
import pytest
from app.services import vin_vinstate

VIN = "XLRTE47MS0E774889"


class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        return json.dumps(self.value).encode()


def documented_fixture(vin=VIN):
    return {
        "success": True,
        "request_id": "mock-id",
        "data": [{"vin": vin, "decoded": {
            "vehicle": {"car": "2014 DAF FT"},
            "wmi": {"make": "DAF"},
        }}],
        "meta": {
            "billed": True,
            "funding_source": "included",
            "included_requests_charged": 1,
            "charged_credits": 0,
        },
    }


def test_documented_payload_never_guesses_model_year_from_label():
    result = vin_vinstate.parse(documented_fixture(), VIN)
    assert result["vehicle"] == {"manufacturer": "DAF"}
    assert result["vehicle_label"] == "2014 DAF FT"
    assert result["status"] == "reported"
    assert result["billing"]["funding_source"] == "included"
    assert result["billing"]["charged_credits"] == 0


def test_explicit_attributes_can_be_used_without_inference():
    payload = documented_fixture()
    payload["data"][0]["decoded"]["vehicle"].update(
        {"model": "XF", "year": 2014, "body_type": "Truck",
         "transmission": "Manual", "engine_displacement_l": 12.9}
    )
    result = vin_vinstate.parse(payload, VIN)
    assert result["vehicle"]["year"] == 2014
    assert result["vehicle"]["transmission"] == "Manual"
    assert result["vehicle"]["engine_displacement_l"] == "12.9"


def test_vin_mismatch_never_merges_foreign_attributes():
    assert vin_vinstate.parse(documented_fixture("YV4A22PK2G1092943"), VIN)["vehicle"] == {}


def test_key_alone_does_not_enable_network(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_VINSTATE_API_KEY", "mock-test-key")
    monkeypatch.delenv("WAREHOUSE_VINSTATE_TEST_ENABLED", raising=False)
    monkeypatch.setattr(vin_vinstate, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Unexpected live call")))
    assert vin_vinstate.test_gate_enabled() is False
    with pytest.raises(RuntimeError, match="disabled"):
        vin_vinstate.decode(VIN)


def test_explicit_staging_gate_sends_bearer_to_documented_endpoint(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_VINSTATE_TEST_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_VINSTATE_API_KEY", "mock-test-key")
    def fake_open(request, timeout):
        assert request.full_url == "https://vinstate.com/api/v1/vin/" + VIN
        assert request.get_header("Authorization") == "Bearer mock-test-key"
        assert timeout == 18
        return Response(documented_fixture())
    monkeypatch.setattr(vin_vinstate, "urlopen", fake_open)
    result = vin_vinstate.decode(VIN)
    assert result["vehicle"]["manufacturer"] == "DAF"


def test_paid_vin_gate_remains_separate(logged, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_VINSTATE_TEST_ENABLED", "false")
    # No test can enable wallet charging with the presence of a VINState key.
    body = {"vin": VIN, "request_key": "vinstate-contract-test-001",
            "expected_amount_minor": 5000, "currency": "UAH", "confirmed": True}
    assert logged.post("/api/v1/vehicles/vin/paid/confirm", json=body).status_code == 503
    # Staging diagnostic route requires an explicit platform admin and quota approval.
    response = logged.post("/api/v1/vehicles/vin/vinstate/preview",
                           json={"vin": VIN, "acknowledge_provider_quota": True})
    assert response.status_code in (403, 503)
