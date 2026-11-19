"""Offline TecAlliance VIN v1 normalization contracts: no network or payments."""
import pytest
from app.services import vin_tecalliance

VIN = "XLRTE47MS0E774889"


def candidate(ktype=None, ntype=None, gearbox=None):
    data = {
        "vehicleInformation": {
            "make": "DAF" if ntype else "VOLVO",
            "model": "FT" if ntype else "XC90",
            "ktype": ktype,
            "ntype": ntype,
            "capacityLiters": 12.9 if ntype else 2.0,
            "powerKW": 300 if ntype else 235,
            "salesStartDate": 201501,
            "bodyName": "Truck" if ntype else "SUV",
        },
        "engine": [{"code": "MX-13" if ntype else "B4204T27", "fuel": "Diesel" if ntype else "Petrol"}],
        "gearbox": gearbox if gearbox is not None else [{"type": "Manual"}],
    }
    return data


def test_commercial_ntype_retained_with_explicit_attributes_only():
    result = vin_tecalliance.normalize_response({"vehicles": [candidate(ntype=123456)]})
    assert result["status"] == "single_candidate"
    assert result["candidate_count"] == 1
    c = result["candidates"][0]
    assert c["ntype"] == 123456 and c["ktype"] is None
    assert c["vehicle"]["vehicle_type"] == "Вантажний автомобіль"
    assert c["vehicle"]["engine_code"] == "MX-13"
    assert c["vehicle"]["transmission"] == "Manual"
    assert "year" not in c["vehicle"]
    assert c["sales_period"]["start"] == "201501"
    assert result["factory_configuration_verified"] is False


def test_multiple_valid_matches_require_user_selection():
    result = vin_tecalliance.normalize_response({"vehicles": [
        candidate(ktype=245600), candidate(ktype=245601),
    ]})
    assert result["candidate_count"] == 2
    assert result["status"] == "multiple_candidates"
    assert result["requires_user_selection"] is True
    assert result["candidates"][0]["ktype"] == 245600
    assert result["candidates"][1]["ktype"] == 245601


def test_ambiguous_gearboxes_not_mapped_as_actual_equipment():
    result = vin_tecalliance.normalize_response({"vehicles": [
        candidate(ktype=1, gearbox=[{"type": "Manual"}, {"type": "Automatic"}]),
    ]})
    c = result["candidates"][0]
    assert c["gearbox_options"] == 2
    assert result["requires_user_selection"]
    assert "transmission" not in c["vehicle"]


def test_no_tecdoc_identifier_not_a_verified_match():
    result = vin_tecalliance.normalize_response({"vehicles": [
        candidate(), candidate(ntype=300),
    ]})
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["ntype"] == 300


def test_invalid_or_oversized_shape_is_rejected_safely():
    with pytest.raises(ValueError):
        vin_tecalliance.normalize_response({"vehicles": "not-a-list"})
    with pytest.raises(ValueError):
        vin_tecalliance.normalize_response({"vehicles": [candidate(ktype=i + 1) for i in range(41)]})
    with pytest.raises(ValueError):
        vin_tecalliance.normalize_vin("BADVIN")
    assert vin_tecalliance.normalize_response({"data": {"vehicles": []}})["status"] == "no_match"


def test_readiness_never_enables_calls_just_from_key(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_TECALLIANCE_API_KEY", "secret-should-not-leak")
    monkeypatch.setenv("WAREHOUSE_TECALLIANCE_COUNTRY", "UA")
    result = vin_tecalliance.readiness()
    assert result["credentials_configured"] is True
    assert result["country_valid"] is True
    assert result["transport_enabled"] is False
    assert result["billing_enabled"] is False
    assert "secret-should-not-leak" not in str(result)


def test_readiness_requires_platform_admin(logged):
    r = logged.get("/api/v1/vehicles/vin/tecalliance/readiness")
    assert r.status_code in (200, 403), r.text
    if r.status_code == 200:
        assert r.json()["transport_enabled"] is False
