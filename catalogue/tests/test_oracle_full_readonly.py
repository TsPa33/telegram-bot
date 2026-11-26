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


def test_vehicle_audit_preserves_distinct_oems_and_uncategorized_counts(monkeypatch):
    @contextmanager
    def db(operation):
        assert operation == "audit_commercial"
        yield None

    def graph_rows(_conn, sql, args, *, stage, started):
        assert "FROM commercial_vehicle_pds FORCE INDEX (PRIMARY)" in sql
        assert "WHERE commertialvehicleid=%s" in sql
        assert args == (8387,) and stage == "audit_pds"
        for node, product, supplier in [(10, 1, 7), (10, 2, 7), (11, 1, 7), (12, 3, 8)]:
            yield dict(category_id=node, product_id=product, supplier_id=supplier)

    def graph_links(_conn, car, linkage, started, *, include_unclassified):
        assert (car, linkage, include_unclassified) == (8387, 16, True)
        for product, supplier, article in [(1, 7, b"A"), (2, 7, b"A"), (2, 7, b"B"),
                                          (4, 8, b"C"), (None, 8, b"D")]:
            yield dict(product_id=product, supplier_id=supplier, article_key=article)

    def oem_batches(_conn, keys, manufacturer, started):
        assert keys == [(7, "A"), (7, "B"), (8, "C"), (8, "D")]
        assert manufacturer == 24
        yield keys, {(7, "A"): {"OE1", "OE2"}, (7, "B"): {"OE2"}, (8, "D"): {"OE3"}}

    monkeypatch.setenv("ORACLE_COMMERCIAL_LINKAGE_TYPE", "16")
    monkeypatch.setattr(oracle, "database", db)
    monkeypatch.setattr(oracle, "audit_identity", lambda *args: 24)
    monkeypatch.setattr(oracle, "graph_rows", graph_rows)
    monkeypatch.setattr(oracle, "graph_links", graph_links)
    monkeypatch.setattr(oracle, "graph_oem_batches", oem_batches)
    result = oracle.vehicle_audit("commercial", 8387)
    assert result["prd_links"] == 4
    assert result["unique_part_types"] == 3
    assert result["unique_articles"] == 4
    assert result["articles_with_oem"] == 3
    assert result["articles_without_oem"] == 1
    assert result["unique_oem_codes"] == 3
    assert result["oem_coverage_percent"] == 75.0
    assert [(item["category_id"], item["prd_links"], item["unique_part_types"],
             item["unique_articles"], item["articles_with_oem"], item["unique_oem_codes"],
             item["oem_coverage_percent"]) for item in result["categories"]] == [
        (None, 0, 0, 2, 1, 1, 50.0), (10, 2, 2, 2, 2, 2, 100.0),
        (11, 1, 1, 1, 1, 2, 100.0), (12, 1, 1, 0, 0, 0, None),
    ]


def test_vehicle_articles_limits_oem_reads_to_the_page_and_matches_binary_ids(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): return False

        def execute(self, sql, args):
            calls.append((sql, args))
            if "FROM article_links" in sql:
                assert "ORDER BY supplier_id, article_key LIMIT %s, %s" in sql
                assert "JOIN" not in sql
                self.rows = [dict(supplier_id=7, article_key=key) for key in (b"A", b"a", b"next")]
            else:
                assert "FROM article_oe FORCE INDEX (supplierid)" in sql
                self.rows = [
                    dict(supplier_id=7, article_key=b"A", oem_key=b"OEM1"),
                    dict(supplier_id=7, article_key=b"A", oem_key=b"OEM1"),
                    dict(supplier_id=7, article_key=b"next", oem_key=b"OEM2"),
                ]

        def fetchall(self): return self.rows

    class DB:
        def cursor(self): return Cursor()

    @contextmanager
    def db(operation):
        assert operation == "articles_passenger"
        yield DB()

    monkeypatch.setattr(oracle, "database", db)
    monkeypatch.setattr(oracle, "audit_identity", lambda *args: 16)
    result = oracle.audit_articles("passenger", 21, 11, 2)
    assert [args for _, args in calls] == [(21, 2, 11, 3), (7, "A", 7, "a", 16)]
    assert result["truncated"] is True and result["next_offset"] == 13
    assert result["items"] == [
        {"supplier_id": 7, "article_number": "A", "oem_count": 1},
        {"supplier_id": 7, "article_number": "a", "oem_count": 0},
    ]


def test_audit_returns_more_than_256_nodes_and_keeps_full_totals_on_pages(monkeypatch):
    @contextmanager
    def db(_operation):
        yield None

    def pds_rows(*args, **kwargs):
        return (dict(category_id=i, product_id=i, supplier_id=7) for i in range(640))

    monkeypatch.setenv("ORACLE_ADAPTER_KEY", "test-key")
    monkeypatch.setattr(oracle, "database", db)
    monkeypatch.setattr(oracle, "audit_identity", lambda *args: 16)
    monkeypatch.setattr(oracle, "graph_rows", pds_rows)
    monkeypatch.setattr(oracle, "graph_links", lambda *args, **kwargs: ())
    client = TestClient(oracle.app, headers={"X-Oracle-Adapter-Key": "test-key"})
    path = "/api/v1/oracle/vehicles/21/audit?kind=passenger"

    unpaged = client.get(path)
    assert unpaged.status_code == 200
    full = unpaged.json()
    assert len(full["categories"]) == full["prd_links"] == full["unique_part_types"] == 640
    assert "next_offset" not in full
    results = [client.get(path + f"&offset={offset}&limit=100").json() for offset in range(0, 640, 100)]
    assert [category for page in results for category in page["categories"]] == full["categories"]
    assert all(page["category_total"] == page["prd_links"] == 640 for page in results)
    assert [page["next_offset"] for page in results] == [100, 200, 300, 400, 500, 600, None]
    assert client.get(path + "&limit=101").status_code == 422


def test_gateway_accepts_audit_category_pages_and_legacy_summary(monkeypatch):
    categories = [{"category_id": node} for node in range(257)]
    received = []

    def request(path, params, **kwargs):
        assert path == "/api/v1/oracle/vehicles/21/audit"
        assert kwargs == {"audit_summary": True, "modification_lookup": True}
        received.append(params)
        body = oracle.audit_response(21, "passenger", 16)
        body["categories"] = categories
        if "offset" in params:
            start, limit = params["offset"], params["limit"]
            more = start + limit < len(categories)
            body.update(categories=categories[start:start + limit], category_total=len(categories),
                        truncated=more, next_offset=start + limit if more else None)
        return body

    monkeypatch.setattr(gateway, "_request", request)
    app = FastAPI()
    app.include_router(gateway.build_router(lambda: None))
    client = TestClient(app)
    path = "/api/v1/oracle/vehicles/21/audit?kind=passenger"
    assert len(client.get(path).json()["categories"]) == 257
    tail = client.get(path + "&offset=250&limit=10")
    assert tail.status_code == 200 and tail.json()["categories"] == categories[250:]
    assert received == [{"kind": "passenger"}, {"kind": "passenger", "offset": 250, "limit": 10}]
