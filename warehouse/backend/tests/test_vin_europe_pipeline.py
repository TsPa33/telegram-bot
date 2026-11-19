"""VIN provider orchestration: opt-in provider, conflicts and provenance (offline)."""
import json
from app.services import vin_lookup, vin_freevindecoder, vin_europe

VIN = "XLRTE47MS0E774889"

class Response:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, *args):
        return json.dumps({"Results": [{"Make":"DAF","Model":"FT","ErrorCode":"0"}]}).encode()

def test_european_enrichment_merges_missing_fields_without_replacing_original(monkeypatch):
    vin_lookup.clear_cache()
    monkeypatch.setattr(vin_lookup, "urlopen", lambda *a, **kw: Response())
    monkeypatch.setattr(vin_freevindecoder, "decode_page", lambda vin: None)
    monkeypatch.setattr(vin_freevindecoder, "source_status", lambda vin: "no_data_or_access_unavailable")
    monkeypatch.setenv('WAREHOUSE_VINCARIO_ENABLED', 'true')
    monkeypatch.setenv('WAREHOUSE_VINCARIO_API_KEY', 'test-key')
    monkeypatch.setenv('WAREHOUSE_VINCARIO_SECRET_KEY', 'test-secret')
    monkeypatch.setattr(vin_europe, "europe_vin", lambda vin: {
        "manufacturer":"DAF", "model":"Different model", "year":2014,
        "fuel_type":"Diesel","engine_displacement_l":"12.9"})
    data=vin_lookup.lookup(VIN)
    assert data["vehicle"]["manufacturer"]=="DAF"
    assert data["vehicle"]["model"]=="FT"
    assert data["vehicle"]["year"]==2014
    assert data["field_sources"]["year"]=="Vincario"
    assert data["conflicts"]["model"]["secondary"]=="Different model"
    assert data["provider_status"]["Vincario"]=="reported"

def test_european_provider_unavailable_is_not_a_failed_lookup(monkeypatch):
    vin_lookup.clear_cache()
    monkeypatch.setattr(vin_lookup,"urlopen",lambda *a,**kw:Response())
    monkeypatch.setattr(vin_freevindecoder,"decode_page",lambda vin:None)
    monkeypatch.setattr(vin_freevindecoder,"source_status",lambda vin:"no_data_or_access_unavailable")
    monkeypatch.setattr(vin_europe,"europe_vin",lambda vin: (_ for _ in ()).throw(OSError("provider offline")))
    data=vin_lookup.lookup(VIN)
    assert data["vehicle"]["manufacturer"]=="DAF"
    assert data["provider_status"]["Vincario"]=="unavailable_or_invalid_response"
