"""Vincario balance-only contract tests; no live calls and no VIN decoding."""
import hashlib
import json
from app.services import vin_vincario_balance as balance


def test_balance_checksum_has_no_vin():
    key, secret = "mock_key", "mock_secret"
    expected = hashlib.sha1(b"balance|mock_key|mock_secret").hexdigest()[:10]
    assert balance._endpoint(key, secret) == (
        f"https://api.vincario.com/3.2/mock_key/{expected}/balance.json"
    )


def test_balance_parser_allowlists_only_nonnegative_integer_counts():
    r = balance.parse_balance({
        "API Decode": 20, "API OEM VIN Lookup": 0,
        "API Vehicle Market Value": "20",
        "secret": "never echo me", "message": "private",
    })
    assert r["status"] == "reported"
    assert r["balances"] == {"API Decode": 20, "API OEM VIN Lookup": 0}
    assert "never echo me" not in str(r)
    assert r["paid_requests_enabled"] is False


def test_balance_parser_does_not_guess_unknown_account_shapes():
    assert balance.parse_balance({"balance": 20})["status"] == "unexpected_schema"
    assert balance.parse_balance(["wrong"])["status"] == "invalid_response"
    assert balance.parse_balance({"API Decode": -1})["status"] == "unexpected_schema"


def test_key_presence_does_not_enable_decode_or_balance_network(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "production")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_API_KEY", "mock_key")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_SECRET_KEY", "mock_secret")
    monkeypatch.setattr(balance, "urlopen", lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("Network invoked")))
    assert balance.fetch_balance()["status"] == "staging_only"


def test_explicit_staging_balance_uses_only_balance_endpoint(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_API_KEY", "mock_key")
    monkeypatch.setenv("WAREHOUSE_VINCARIO_SECRET_KEY", "mock_secret")
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, *args):
            return json.dumps({"API Decode": 19, "API OEM VIN Lookup": 0}).encode()
    def fetch(request, timeout):
        assert request.full_url == balance._endpoint("mock_key", "mock_secret")
        assert "/decode/" not in request.full_url
        assert timeout == 12
        return FakeResponse()
    monkeypatch.setattr(balance, "urlopen", fetch)
    r = balance.fetch_balance()
    assert r["status"] == "reported"
    assert r["balances"]["API Decode"] == 19


def test_balance_endpoint_not_accessible_without_platform_admin(logged, monkeypatch):
    from app.api import vin_vincario_balance as route
    monkeypatch.setattr(route, "platform_admin", lambda user: False)
    monkeypatch.setattr(route, "fetch_balance", lambda: (_ for _ in ()).throw(AssertionError("Unauthorized request triggered provider")))
    response = logged.post("/api/v1/vehicles/vin/vincario/balance")
    assert response.status_code == 403


def test_decoder_missing_is_not_equated_to_zero():
    report = balance.parse_balance({"API Stolen Check": 5, "API Vehicle Market Value": 5})
    assert report["status"] == "reported"
    assert report["decode_balance_status"] == "not_returned"
    assert report["decode_balance"] is None
    assert report["free_trial_verified"] is False
    assert all(f["name"] != "API Decode" for f in report["provider_balance_fields"])


def test_alternate_decoder_name_is_recognized():
    report = balance.parse_balance({"API VIN Decode": 20, "API Stolen Check": 5})
    assert report["decode_balance"] == 20
    assert report["decode_balance_status"] == "available"
    assert report["balances"]["API Decode"] == 20
    assert report["free_trial_verified"] is False


def test_decoder_zero_is_distinguishable_from_missing():
    report = balance.parse_balance({"API Decode": 0})
    assert report["decode_balance_status"] == "available"
    assert report["decode_balance"] == 0


def test_diagnostic_never_reflects_unknown_sensitive_keys_or_values():
    report = balance.parse_balance({
        "API Decode": "unrecognized", "Secret Key": "SECRET_VALUE",
        "API Token": "TOKEN_VALUE", "customer_email": "private@example.com",
        "VIN Decode Extra": 0,
    })
    assert report["decode_balance_status"] == "unexpected_value_type"
    assert report["decode_balance"] is None
    assert report["provider_balance_fields"] == [
        {"name": "API Decode", "type": "text"},
        {"name": "VIN Decode Extra", "type": "integer"},
    ]
    for value in ("SECRET_VALUE", "TOKEN_VALUE", "private@example.com"):
        assert value not in str(report)
