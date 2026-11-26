"""Offline contract regression tests; no DB connection or writes."""
from contextlib import contextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient
from oracle_adapter import app as oracle
import oracle_gateway as gateway


def test_source_pages_namespace_and_pagination(monkeypatch):
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, args):
            queries.append((sql, args))
            assert sql.lstrip().startswith("SELECT")
        def fetchall(self):
            return [{"node_id": 10, "product_id": 20, "supplier_id": 30},
                    {"node_id": 11, "product_id": 21, "supplier_id": 31}]
    class DB:
        def cursor(self): return Cursor()
    @contextmanager
    def db(): yield DB()
    monkeypatch.setattr(oracle, "database", db)
    monkeypatch.setattr(oracle, "audit_identity", lambda *_: 106)
    monkeypatch.setenv("ORACLE_ADAPTER_KEY", "test-key")
    api = TestClient(oracle.app)
    path = "/api/v1/oracle/vehicles/18248/prd-page"
    assert api.get(path, params={"kind": "commercial"}).status_code == 401
    auth = {"X-Oracle-Adapter-Key": "test-key"}
    response = api.get(path, params={"kind": "commercial", "offset": 4, "limit": 1}, headers=auth)
    assert response.status_code == 200
    data = response.json()
    assert data["kind"] == "commercial" and data["next_offset"] == 5
    assert data["fitment_verified"] is False and data["source_association_only"] is True
    assert "commercial_vehicle_pds" in queries[0][0]
    assert queries[0][1] == (18248, 4, 2)
    assert api.get(path, params={"kind": "unknown"}, headers=auth).status_code == 422


def test_named_pages_gateway_scope(monkeypatch):
    calls = []
    def request(path, params, **kwargs):
        calls.append((path, params))
        return {"source": "oracle", "source_modification_id": 18248,
                "kind": "passenger", "manufacturer_id": 106, "fitment_verified": False,
                "source_association_only": True, "items": [], "truncated": False,
                "next_offset": None, "product_id": 402}
    monkeypatch.setattr(gateway, "_request", request)
    app = FastAPI()
    app.include_router(gateway.build_router(lambda: None))
    api = TestClient(app)
    base = "/api/v1/oracle/vehicles/18248/"
    for endpoint in ("prd-page", "products", "categories"):
        assert api.get(base + endpoint, params={"kind": "passenger"}).status_code == 200
    assert api.get(base + "part-articles", params={"kind": "passenger", "product_id": 402}).status_code == 200
    assert calls[-1][1]["product_id"] == 402
    assert api.get(base + "part-articles", params={"kind": "passenger", "product_id": 403}).status_code == 503
