"""Focused offline API contract tests; no Oracle connection or provider credits."""
import sys
from pathlib import Path
from contextlib import contextmanager

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "oracle_adapter"))
import app as oracle


class FakeCursor:
    def __init__(self, queries, rows):
        self.queries = queries
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, args):
        self.queries.append((statement, args))
        assert statement.lstrip().startswith("SELECT ")
        assert "article_li" not in statement.lower()
        assert "article_links" not in statement.lower()

    def fetchall(self):
        return self.rows


class FakeDb:
    def __init__(self, rows):
        self.queries = []
        self.rows = rows

    def cursor(self):
        return FakeCursor(self.queries, self.rows)


@contextmanager
def mock_database(fake):
    yield fake


def client(monkeypatch, rows):
    db = FakeDb(rows)
    monkeypatch.setattr(oracle, "database", lambda: mock_database(db))
    monkeypatch.setenv("ORACLE_ADAPTER_KEY", "test-internal-key")
    return TestClient(oracle.app), db


def auth():
    return {"X-Oracle-Adapter-Key": "test-internal-key"}


def test_oem_by_article_uses_composite_index_and_exact_reference(monkeypatch):
    api, db = client(monkeypatch, [{"oem_number": "272440"}, {"oem_number": "31256231"}])
    r = api.get("/api/v1/oracle/oem/by-article", params={"supplier_id": 1,
                "article_number": "20064", "manufacturer_id": 120}, headers=auth())
    assert r.status_code == 200
    assert r.json()["fitment_verified"] is False
    assert [v["oem_number"] for v in r.json()["items"]] == ["272440", "31256231"]
    sql, args = db.queries[0]
    assert "FORCE INDEX (supplierid)" in sql
    assert args == (1, "20064", "20064", 120, 21)


def test_oem_reverse_lookup_uses_index_and_explicit_non_fitment(monkeypatch):
    api, db = client(monkeypatch, [{"supplier_id": 1, "article_number": "20064"},
                                      {"supplier_id": 23, "article_number": "755104"}])
    r = api.get("/api/v1/oracle/oem/by-number", params={"manufacturer_id": 120,
                 "oem_number": "272440", "limit": 1}, headers=auth())
    assert r.status_code == 200
    assert r.json()["truncated"] is True
    assert r.json()["items"] == [{"supplier_id": 1, "article_number": "20064"}]
    assert "FORCE INDEX (OENbr)" in db.queries[0][0]
    assert db.queries[0][1] == ("272440", "272440", 120, 2)


def test_car_prd_is_not_exact_vin_fitment(monkeypatch):
    api, db = client(monkeypatch, [{"node_id": 100030, "product_id": 402, "supplier_id": 2}])
    r = api.get("/api/v1/oracle/vehicles/107555/prd", headers=auth())
    assert r.status_code == 200
    assert r.json()["source_association_only"] is True
    assert r.json()["fitment_verified"] is False
    assert "FORCE INDEX (PRIMARY)" in db.queries[0][0]
    assert db.queries[0][1] == (107555, 21)


def test_auth_and_invalid_numbers(monkeypatch):
    api, db = client(monkeypatch, [])
    endpoint = "/api/v1/oracle/oem/by-number"
    assert api.get(endpoint, params={"manufacturer_id": 120, "oem_number": "272440"}).status_code == 401
    assert api.get(endpoint, params={"manufacturer_id": 120, "oem_number": "272440\n"},
                   headers=auth()).status_code == 422
    assert api.get(endpoint, params={"manufacturer_id": 120, "oem_number": "272440", "limit": 51},
                   headers=auth()).status_code == 422
    assert db.queries == []


def test_rejects_root_or_public_database(monkeypatch):
    for k, v in {"ORACLE_MYSQL_PORT": "3306", "ORACLE_MYSQL_USER": "root",
                 "ORACLE_MYSQL_PASSWORD": "test", "ORACLE_MYSQL_DATABASE": "td1q2018",
                 "ORACLE_MYSQL_HOST": "127.0.0.1"}.items():
        monkeypatch.setenv(k, v)
    from fastapi import HTTPException
    try:
        oracle.require_database_settings()
        assert False, "root must be rejected"
    except HTTPException as e:
        assert e.status_code == 503
    monkeypatch.setenv("ORACLE_MYSQL_USER", "carpot_catalogue_ro")
    monkeypatch.setenv("ORACLE_MYSQL_HOST", "0.0.0.0")
    try:
        oracle.require_database_settings()
        assert False, "public MySQL host must be rejected"
    except HTTPException as e:
        assert e.status_code == 503
