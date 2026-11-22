"""Offline, zero-credential, zero-network tests for Oracle catalogue gateway."""
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracle_gateway as gateway


def client(monkeypatch, payload=None):
    app = FastAPI()
    def auth():
        return None
    app.include_router(gateway.build_router(auth))
    if payload is not None:
        monkeypatch.setattr(gateway, "_request", lambda *_: payload)
    return TestClient(app)


def enabled(monkeypatch):
    monkeypatch.setenv("ORACLE_CATALOGUE_ENABLED", "true")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "catalogue-staging")
    monkeypatch.setenv("ORACLE_ADAPTER_URL", "https://example.org")
    monkeypatch.setenv("ORACLE_ADAPTER_KEY", "test-secret")


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ORACLE_CATALOGUE_ENABLED", raising=False)
    response = client(monkeypatch).get("/api/v1/oracle/oem/by-number",
        params={"manufacturer_id": 120, "oem_number": "272440"})
    assert response.status_code == 503


def test_staging_only_and_https_required(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(HTTPException) as e:
        gateway._settings()
    assert e.value.status_code == 503
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "catalogue-staging")
    monkeypatch.setenv("ORACLE_ADAPTER_URL", "http://example.org")
    with pytest.raises(HTTPException):
        gateway._settings()


def test_oem_and_prd_contracts_do_not_assert_fitment(monkeypatch):
    enabled(monkeypatch)
    api = client(monkeypatch, {"items": [{"oem_number": "272440"}], "truncated": False})
    r = api.get("/api/v1/oracle/oem/by-article", params={"manufacturer_id": 120,
            "supplier_id": 1, "article_number": "20064"})
    assert r.status_code == 200
    assert r.json()["items"] == [{"oem_number": "272440"}]
    assert r.json()["fitment_verified"] is False
    api = client(monkeypatch, {"items": [{"supplier_id": 23, "article_number": "755104"}],
                                    "truncated": True})
    r = api.get("/api/v1/oracle/oem/by-number", params={"manufacturer_id": 120,
            "oem_number": "272440"})
    assert r.status_code == 200 and r.json()["cross_reference_only"] is True
    api = client(monkeypatch, {"items": [{"node_id": 100030, "product_id": 402,
                                          "supplier_id": 2}], "truncated": False})
    r = api.get("/api/v1/oracle/vehicles/107555/prd")
    assert r.status_code == 200 and r.json()["fitment_verified"] is False


def test_untrusted_payload_rejected(monkeypatch):
    enabled(monkeypatch)
    api = client(monkeypatch, {"items": [{"article_number": "x", "supplier_id": "bad"}],
                                    "truncated": False})
    assert api.get("/api/v1/oracle/oem/by-number",
                   params={"manufacturer_id": 120, "oem_number": "272440"}).status_code == 503


def test_http_is_never_fallback(monkeypatch):
    enabled(monkeypatch)
    monkeypatch.setenv("ORACLE_ADAPTER_URL", "http://127.0.0.1:8081")
    with pytest.raises(HTTPException):
        gateway._settings()
