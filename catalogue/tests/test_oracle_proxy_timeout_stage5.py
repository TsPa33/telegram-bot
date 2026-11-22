"""Focused offline regression tests for Oracle private CONNECT proxy."""
import logging
import sys
from pathlib import Path
import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracle_gateway as gateway


def test_proxy_timeout_and_diagnostic_secrecy(monkeypatch, caplog):
    observed = {}
    monkeypatch.setattr(gateway, "_settings", lambda: (
        "https://carpot-oracle.tailf95906.ts.net", "sensitive-secret-value",
        "http://carpot-oracle-relay.railway.internal:1055"))

    class FakeClient:
        def __init__(self, **kwargs):
            observed.update(kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def stream(self, *args, **kwargs):
            observed["headers"] = kwargs["headers"]
            raise httpx.ConnectTimeout("sensitive-secret-value: network timeout")

    monkeypatch.setattr(gateway.httpx, "Client", FakeClient)
    with caplog.at_level(logging.WARNING, logger="carpot.oracle_gateway"):
        with pytest.raises(HTTPException) as error:
            gateway._request("/api/v1/oracle/oem/by-article", {"supplier_id": 1})
    assert error.value.status_code == 503
    assert observed["timeout"].connect == 8.0
    assert observed["proxy"] == "http://carpot-oracle-relay.railway.internal:1055"
    assert observed["headers"]["X-Oracle-Adapter-Key"] == "sensitive-secret-value"
    assert "kind=ConnectTimeout" in caplog.text
    assert "sensitive-secret-value" not in caplog.text


def test_rejects_untrusted_proxy(monkeypatch):
    monkeypatch.setenv("ORACLE_CATALOGUE_ENABLED", "true")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "catalogue-staging")
    monkeypatch.setenv("ORACLE_ADAPTER_URL", "https://carpot-oracle.tailf95906.ts.net")
    monkeypatch.setenv("ORACLE_ADAPTER_KEY", "not-printed")
    monkeypatch.setenv("ORACLE_HTTP_PROXY", "http://outside.example:1055")
    with pytest.raises(HTTPException) as error:
        gateway._settings()
    assert error.value.status_code == 503
