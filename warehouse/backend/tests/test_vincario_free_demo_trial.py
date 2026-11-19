"""Vincario Free Demo: mocked network only, zero live provider calls."""
import json
from app.services import vin_vincario_trial as trial

DAF = "XLRTE47MS0E774889"


def fixture():
    return {"decode": [
        {"label": "Make", "value": "DAF"},
        {"label": "Model", "value": "XF"},
        {"label": "Model Year", "value": 2007},
        {"label": "Body", "value": "Tractor"},
        {"label": "Engine Displacement (ccm)", "value": 12902},
        {"label": "Fuel Type - Primary", "value": "Diesel"},
        {"label": "Drive", "value": "Rear-wheel drive"},
        {"label": "Make Logo", "value": "https://example.com/brand.svg"},
        {"label": "Unexpected Field", "value": "should never leak"},
    ]}


def test_daf_decode_maps_confirmed_web_report_fields():
    r = trial.parse_decode(fixture(), DAF)
    assert r["status"] == "reported"
    assert r["vehicle"]["manufacturer"] == "DAF"
    assert r["vehicle"]["year"] == 2007
    assert r["vehicle"]["engine_displacement_cc"] == "12902"
    assert r["vehicle"]["body_class"] == "Tractor"
    assert r["vehicle"]["drive_type"] == "Rear-wheel drive"
    assert "transmission" in r["missing"]
    assert "engine_code" in r["missing"]
    assert r["logo_field_available"] is True
    assert "brand.svg" not in str(r)
    assert "should never leak" not in str(r)


def test_invalid_year_does_not_infer_model_year():
    doc = fixture()
    doc["decode"].append({"label": "Transmission", "value": "Automatic"})
    doc["decode"][2]["value"] = "not confirmed"
    r = trial.parse_decode(doc, DAF)
    assert "year" not in r["vehicle"]
    assert r["vehicle"]["transmission"] == "Automatic"


def test_only_three_control_vins(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_API_KEY", "test-key")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_SECRET_KEY", "test-secret")
    monkeypatch.setattr(trial, "urlopen", lambda *a,**k: (_ for _ in ()).throw(AssertionError("unexpected call")))
    assert trial.preview("WVWZZZ1JZXW000001", acknowledged=True)["status"] == "vin_not_allowlisted"
    assert trial.preview(DAF, acknowledged=False)["status"] == "confirmation_required"


def test_balance_floor_blocks_all_provider_decodes(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_API_KEY", "test-key")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_SECRET_KEY", "test-secret")
    monkeypatch.setattr(trial, "fetch_balance", lambda: {"decode_balance": 17})
    monkeypatch.setattr(trial, "urlopen", lambda *a,**k: (_ for _ in ()).throw(AssertionError("unexpected decode")))
    trial._results.clear()
    assert trial.preview(DAF, acknowledged=True)["status"] == "insufficient_verified_demo_balance"


def test_trial_once_and_repeated_request_hits_cache(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_API_KEY", "test-key")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_SECRET_KEY", "test-secret")
    checks = iter((20,19))
    monkeypatch.setattr(trial, "fetch_balance", lambda: {"decode_balance": next(checks)})
    calls = []
    class FakeResponse:
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def read(self,*a):return json.dumps(fixture()).encode()
    def fake_open(request, timeout):
        calls.append(request.full_url)
        assert request.full_url == trial._endpoint(DAF, "test-key", "test-secret")
        assert timeout == 20
        return FakeResponse()
    monkeypatch.setattr(trial, "urlopen", fake_open)
    trial._results.clear()
    first = trial.preview(DAF, acknowledged=True)
    second = trial.preview(DAF, acknowledged=True)
    assert first["status"] == "reported"
    assert first["balance_before"] == 20
    assert first["balance_after"] == 19
    assert second["from_cache"] is True
    assert len(calls) == 1
    trial._results.clear()


def test_cannot_run_without_platform_admin(logged, monkeypatch):
    from app.api import vin_vincario_trial as route
    monkeypatch.setattr(route, "platform_admin", lambda _u: False)
    monkeypatch.setattr(route.vin_vincario_trial, "preview",
                        lambda *_a,**_kw: (_ for _ in ()).throw(AssertionError("provider called")))
    r = logged.post("/api/v1/vehicles/vin/vincario/trial/preview",
                    json={"vin":DAF,"acknowledge_free_quota":True})
    assert r.status_code == 403
