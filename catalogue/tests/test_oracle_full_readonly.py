"""Offline contract regression tests; no DB connection or writes."""
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException
import pymysql
import pytest
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
    assert "WHERE commertialvehicleid=%s" in queries[0][0]
    assert "commercialvehicleid" not in queries[0][0]
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



def test_commercial_audit_and_graph_share_the_verified_pds_column(monkeypatch):
    monkeypatch.setenv("ORACLE_COMMERCIAL_LINKAGE_TYPE", "16")
    assert oracle.pds_source("commercial") == ("commercial_vehicle_pds", "commertialvehicleid")
    assert oracle.audit_source("commercial") == (*oracle.pds_source("commercial"), 16)
    assert oracle.audit_source("passenger") == ("passanger_car_pds", "passangercarid", 2)


@pytest.mark.parametrize("value", ["", "2", "7", "14", "19", "23"])
def test_commercial_audit_refuses_other_target_domains(monkeypatch, value):
    monkeypatch.setenv("ORACLE_COMMERCIAL_LINKAGE_TYPE", value)
    with pytest.raises(HTTPException) as error:
        oracle.audit_source("commercial")
    assert error.value.status_code == 503


def test_commercial_linkage_skips_timed_out_witness_and_matches_exact_target(monkeypatch):
    from oracle_adapter import check_source_graph as probe

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, args):
            if "JOIN models" in sql:
                self.rows = [{"car_id": car, "model_id": model} for car, model in
                             [(8346, 100), (14497, 200), (18987, 300)]]
                return
            car = args[0]
            assert args == (car, car, 16)
            assert "WHERE commertialvehicleid=%s" in sql
            assert "p.productid=a.productid AND p.supplierid=a.supplierid" in sql
            assert "a.linkageid=%s AND a.linkagetypeid=%s" in sql
            assert "LIMIT 1" in sql
            if car == 8346:
                raise pymysql.OperationalError(3024, "timeout")
            self.rows = [{"product_id": 5, "supplier_id": 6}]

        def fetchall(self):
            return self.rows

    class DB:
        def cursor(self):
            return Cursor()

    observed = []
    monkeypatch.setattr(probe, "report", lambda label, **details: observed.append((label, details)))
    assert probe.report_commercial_linkage(DB(), {}, [8346, 14497, 18987]) == 16
    assert observed[1][1]["skipped_timeout"] is True
    assert [row["car_id"] for row in observed[-1][1]["witnesses"]] == [14497, 18987]


def test_commercial_linkage_requires_two_models_and_fails_on_real_query_errors(monkeypatch):
    from oracle_adapter import check_source_graph as probe

    def one_model(_conn, label, sql, args=(), **options):
        if label == "commercial_witness_identities":
            return [{"car_id": 10, "model_id": 5539}, {"car_id": 11, "model_id": 5539}]
        if label == "commercial_witness_models":
            return [{"first_model": 200, "last_model": 200}]
        if label == "commercial_witnesses_200":
            return [{"id": 20}]
        if label == "commercial_pds_linkage_10":
            return [{"product_id": 5, "supplier_id": 6}]
        if label == "commercial_pds_linkage_20":
            return None  # Any error other than the allowed timeout remains fatal.
        raise AssertionError(label)

    monkeypatch.setattr(probe, "query", one_model)
    assert probe.report_commercial_linkage(None, {}, [10, 11]) is None
