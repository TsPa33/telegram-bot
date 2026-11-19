"""Paid VIN offer contract: no finance mutation and no paid API calls."""
from fastapi import HTTPException
import pytest
from app.services import vin_paid_contract as paid

VIN = "XLRTE47MS0E774889"


def test_fixed_quote_and_no_live_checkout(logged):
    res = logged.get("/api/v1/vehicles/vin/paid/quote?vin=" + VIN)
    assert res.status_code == 200, res.text
    offer = res.json()
    assert (offer["amount_minor"], offer["currency"]) == (5000, "UAH")
    assert not offer["checkout_available"]
    assert offer["requires_confirmation"] is True


def test_explicit_confirmation_cannot_charge_or_reserve(logged, monkeypatch):
    monkeypatch.setattr(
        "app.services.vin_europe.europe_vin",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Paid decoder must never run")),
    )
    body = dict(
        vin=VIN, request_key="paid-vin-fixture-key-001",
        expected_amount_minor=5000, currency="UAH", confirmed=True,
    )
    r = logged.post("/api/v1/vehicles/vin/paid/confirm", json=body)
    assert r.status_code == 503, r.text
    assert "не списано" in r.json()["detail"]
    assert logged.post("/api/v1/vehicles/vin/paid/confirm", json=body).status_code == 503


def test_price_tampering_and_confirmation_are_blocked(logged):
    body = dict(vin=VIN, request_key="paid-vin-fixture-key-002",
                expected_amount_minor=100, currency="UAH", confirmed=True)
    assert logged.post("/api/v1/vehicles/vin/paid/confirm", json=body).status_code == 409
    body["expected_amount_minor"] = 5000
    body["confirmed"] = False
    assert logged.post("/api/v1/vehicles/vin/paid/confirm", json=body).status_code == 422
    body["confirmed"] = True
    body["currency"] = "USD"
    assert logged.post("/api/v1/vehicles/vin/paid/confirm", json=body).status_code == 409
    assert logged.get("/api/v1/vehicles/vin/paid/quote?vin=INVALID").status_code == 422


def test_no_useful_new_fields_releases_reservation():
    decision = paid.settlement_decision(
        {"manufacturer": "DAF", "model": "FT", "fuel_type": "Дизель"},
        {"manufacturer": "DAF", "model": "FT", "fuel_type": "Дизель", "year": None},
    )
    assert not decision.charge and decision.new_fields == ()
    assert paid.next_state("quoted", "reserve_confirmed") == "reserved"
    assert paid.next_state("reserved", "no_useful_result") == "released"
    assert paid.next_state("released", "no_useful_result") == "released"
    with pytest.raises(ValueError):
        paid.next_state("released", "useful_result")


def test_useful_new_fact_captures_only_once():
    decision = paid.settlement_decision(
        {"manufacturer": "DAF", "model": "FT"},
        {"year": 2014, "body_class": "Truck", "model": "Different"},
    )
    assert decision.charge
    assert decision.new_fields == ("body_class", "year")
    assert paid.next_state("reserved", "useful_result") == "captured"
    assert paid.next_state("captured", "useful_result") == "captured"
    assert not paid.settlement_decision({"year": 2014}, {"year": 2014}).charge
    assert not paid.settlement_decision({}, {"year": "unknown"}).charge


def test_wallet_keys_deterministic_and_scoped():
    a = paid.payment_keys("workspace-a", VIN)
    assert a == paid.payment_keys("workspace-a", VIN.lower())
    assert a != paid.payment_keys("workspace-b", VIN)
    assert len(set(a.values())) == 3


def test_paid_cache_requires_same_tenant_and_authorized_unexpired_receipt():
    receipt = dict(
        workspace_id="a", vin=VIN, product=paid.PRODUCT,
        provider_version="v1", financial_status="captured",
        license_allows_reuse=True, expires_at_epoch=2000,
        confirmed_fields={"year": 2014},
    )
    assert paid.reusable_receipt(receipt,workspace="a",vin=VIN,
                                 provider_version="v1",now_epoch=1000)
    assert not paid.reusable_receipt(receipt,workspace="b",vin=VIN,
                                     provider_version="v1",now_epoch=1000)
    assert not paid.reusable_receipt(receipt,workspace="a",vin=VIN,
                                     provider_version="v1",now_epoch=2000)
    receipt["license_allows_reuse"] = False
    assert not paid.reusable_receipt(receipt,workspace="a",vin=VIN,
                                     provider_version="v1",now_epoch=1000)
