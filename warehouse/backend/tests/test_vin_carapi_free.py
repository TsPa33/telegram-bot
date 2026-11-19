"""Contract tests for optional free CarAPI.dev adapter; all HTTP mocked."""
import json

from app.services import vin_carapi, vin_lookup, vin_freevindecoder

VIN = "XLRTE47MS0E774889"


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        return json.dumps(self.payload).encode()


def test_no_key_means_no_carapi_http(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_CARAPI_TOKEN", raising=False)
    monkeypatch.setenv("WAREHOUSE_CARAPI_ENABLED", "true")
    monkeypatch.setattr(vin_carapi, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("No external call permitted")))
    assert vin_carapi.decode(VIN) is None


def test_specs_mapping_never_infers_year_from_registration_date(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_CARAPI_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_CARAPI_TOKEN", "unit-test-key")
    monkeypatch.setattr(vin_carapi, "urlopen", lambda *a, **kw: Response({
        "vin": VIN,
        "specifications": {"make": "DAF", "model": "XF", "registrationDate": "2014-01-01",
                           "bodyStyle": "TRUCK", "transmission": "automatic",
                           "fuel": "diesel", "enginePower": 300, "enginePowerUnit": "kW"},
        "manufacturer": {"name": "DAF Trucks"},
    }))
    result = vin_carapi.decode(VIN)
    assert result["manufacturer"] == "DAF"
    assert result["body_class"] == "TRUCK"
    assert result["vehicle_type"] == "Вантажний автомобіль"
    assert result["transmission"] == "automatic"
    assert result["engine_power_kw"] == "300"
    assert "year" not in result


def test_data_shape_maps_actual_model_year(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_CARAPI_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_CARAPI_TOKEN", "unit-test-key")
    monkeypatch.setattr(vin_carapi, "urlopen", lambda *a, **kw: Response({
        "success": True, "data": {"make": "Volvo", "model": "XC90", "year": 2016,
                                  "engine": "2.0L", "transmission": "automatic"},
    }))
    assert vin_carapi.decode(VIN)["year"] == 2016


def test_pipeline_does_not_overwrite_primary_and_only_calls_with_sparse_core(monkeypatch):
    vin_lookup.clear_cache()
    monkeypatch.setenv("WAREHOUSE_CARAPI_ENABLED", "true")
    monkeypatch.setenv("WAREHOUSE_CARAPI_TOKEN", "unit-test-key")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_ENABLED", "false")
    monkeypatch.setattr(vin_lookup, "urlopen", lambda *a, **kw: Response({
        "Results": [{"Make": "DAF", "Model": "FT", "ErrorCode": "0"}],
    }))
    monkeypatch.setattr(vin_freevindecoder, "decode_page", lambda vin: None)
    monkeypatch.setattr(vin_freevindecoder, "source_status", lambda vin: "no_data")
    monkeypatch.setattr(vin_carapi, "decode", lambda vin: {
        "manufacturer": "DAF", "model": "XF", "year": 2014,
        "body_class": "TRUCK", "transmission": "automatic"})
    result = vin_lookup.lookup(VIN)
    assert result["vehicle"]["model"] == "FT"
    assert result["vehicle"]["year"] == 2014
    assert result["field_sources"]["year"] == "CarAPI.dev"
    assert result["conflicts"]["model"]["secondary"] == "XF"
    assert result["provider_status"]["CarAPI.dev"] == "reported"
    assert vin_lookup.lookup(VIN)["cached"] is True
