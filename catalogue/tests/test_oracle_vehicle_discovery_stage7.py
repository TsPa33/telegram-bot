"""Offline tests for Oracle vehicle discovery; no DB, secrets or import access."""
from contextlib import contextmanager
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "oracle_adapter"))
import app as oracle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import oracle_gateway as gateway


class Cursor:
    def __init__(self, rows, calls): self.rows, self.calls = rows, calls
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, args):
        normalized=sql.lower()
        assert normalized.lstrip().startswith("select ")
        assert "article_li " not in normalized and "article_links " not in normalized
        self.calls.append((sql,args))
    def fetchall(self): return self.rows


class Conn:
    def __init__(self, rows): self.rows, self.calls = rows, []
    def cursor(self): return Cursor(self.rows, self.calls)


@contextmanager
def fake_db(conn):
    yield conn


def adapter(monkeypatch, rows):
    c=Conn(rows)
    monkeypatch.setattr(oracle, "database", lambda:fake_db(c))
    monkeypatch.setenv("ORACLE_ADAPTER_KEY", "offline-test")
    return TestClient(oracle.app), c


HEADERS={"X-Oracle-Adapter-Key":"offline-test"}


def test_daf_manufacturer_small_table_select_no_vin_claim(monkeypatch):
    api, conn=adapter(monkeypatch,[{"id":88,"name":"DAF"}])
    res=api.get("/api/v1/oracle/vehicles/manufacturers",
        params={"name":"DAF","kind":"commercial"},headers=HEADERS)
    assert res.status_code==200, res.text
    assert res.json()["items"]==[{"id":88,"name":"DAF"}]
    assert res.json()["fitment_verified"] is False
    assert "SELECT DISTINCT id, description AS name FROM manufacturers" in conn.calls[0][0]
    assert "iscommercialvehicle='True'" in conn.calls[0][0]
    assert conn.calls[0][1]==("DAF",21)


def test_daf_commercial_model_and_modification_uses_source_indexes(monkeypatch):
    api, conn=adapter(monkeypatch,[{"id":901,"name":"XF",
                                  "construction_interval":"2005 - 2013"}])
    r=api.get("/api/v1/oracle/vehicles/models",
        params={"manufacturer_id":88,"kind":"commercial"},headers=HEADERS)
    assert r.status_code==200, r.text
    assert r.json()["items"][0]["id"]==901
    assert "SELECT DISTINCT id, description AS name" in conn.calls[0][0]
    assert "models FORCE INDEX (manufacturerid)" in conn.calls[0][0]
    assert conn.calls[0][1]==(88,0,31)
    assert "article_links" not in conn.calls[0][0]
    api, conn=adapter(monkeypatch,[{"id":14200,"model_id":901,
        "name":"XF105 460","construction_interval":"2006 - 2013"}])
    r=api.get("/api/v1/oracle/vehicles/modifications",
        params={"model_id":901,"kind":"commercial","after":100},headers=HEADERS)
    assert r.status_code==200, r.text
    assert r.json()["items"][0]["model_id"]==901
    assert "commercial_vehicles FORCE INDEX (modelid)" in conn.calls[0][0]
    assert conn.calls[0][1]==(901,100,31)


def test_passenger_models_modifications_and_cursor(monkeypatch):
    api, conn=adapter(monkeypatch,[{"id":37773,"name":"XC60 II (246)",
        "construction_interval":"03.2017 -"},
        {"id":37774,"name":"XC60","construction_interval":"2017 -"}])
    r=api.get("/api/v1/oracle/vehicles/models",
        params={"manufacturer_id":120,"kind":"passenger","limit":1},headers=HEADERS)
    assert r.status_code==200, r.text
    assert r.json()["truncated"] is True
    assert r.json()["next_after"]==37773
    assert r.json()["fitment_verified"] is False
    assert conn.calls[0][1]==(120,0,2)
    api,conn=adapter(monkeypatch,[{"id":126478,"model_id":37773,
        "name":"2.0 D4 AWD","construction_interval":"03.2017 -"}])
    r=api.get("/api/v1/oracle/vehicles/modifications",
        params={"model_id":37773,"kind":"passenger"},headers=HEADERS)
    assert r.status_code==200
    assert r.json()["items"][0]["id"]==126478
    assert "passanger_cars FORCE INDEX (modelid)" in conn.calls[0][0]


def test_engine_attributes_passenger_and_commercial(monkeypatch):
    for kind,table,index in [
        ("passenger","passanger_car_attributes","passangercarid"),
        ("commercial","commercial_vehicle_attributes","commercialvehicleid")
    ]:
        api, conn=adapter(monkeypatch,[{
            "attribute_type":"EngineCode","display_value":"B4204T27"
        }])
        r=api.get("/api/v1/oracle/vehicles/attributes",
            params={"car_id":107555,"kind":kind},headers=HEADERS)
        assert r.status_code==200, r.text
        assert r.json()["items"][0]["display_value"]=="B4204T27"
        assert f"FROM {table} FORCE INDEX ({index})" in conn.calls[0][0]
        assert conn.calls[0][1]==(107555,51)


def test_no_public_or_unbounded_database_access(monkeypatch):
    api,conn=adapter(monkeypatch,[])
    assert api.get("/api/v1/oracle/vehicles/models",
        params={"manufacturer_id":120,"kind":"passenger"}).status_code==401
    assert api.get("/api/v1/oracle/vehicles/models",
        params={"manufacturer_id":120,"kind":"commercial","limit":999},
        headers=HEADERS).status_code==422
    assert api.get("/api/v1/oracle/vehicles/modifications",
        params={"model_id":0,"kind":"passenger"},
        headers=HEADERS).status_code==422
    assert api.get("/api/v1/oracle/vehicles/manufacturers",
        params={"name":"%","kind":"commercial"},headers=HEADERS).status_code==422
    assert conn.calls==[]


def test_gateway_validates_source_identity_and_rejects_forged_rows(monkeypatch):
    app=FastAPI()
    app.include_router(gateway.build_router(lambda:None))
    api=TestClient(app)
    monkeypatch.setattr(gateway,"_request",lambda *_: {
        "items":[{"id":126480,"model_id":37773,
                  "name":"2.0 T5 AWD","construction_interval":"03.2017 -"}],
        "truncated":False,"next_after":None,"vehicle_identity_only":True,
        "fitment_verified":False
    })
    r=api.get("/api/v1/oracle/vehicles/modifications",
        params={"model_id":37773,"kind":"passenger"})
    assert r.status_code==200, r.text
    assert r.json()["items"][0]["model_id"]==37773
    assert r.json()["fitment_verified"] is False
    assert r.json()["vehicle_identity_only"] is True
    forged={"items":[{"id":126480,"model_id":123,
                      "name":"2.0 T5 AWD","construction_interval":None}],
           "truncated":False,"next_after":None,"vehicle_identity_only":True,
           "fitment_verified":False}
    monkeypatch.setattr(gateway,"_request",lambda *_:forged)
    assert api.get("/api/v1/oracle/vehicles/modifications",
        params={"model_id":37773,"kind":"passenger"}).status_code==503
    forged["items"][0]["model_id"]=37773
    forged["fitment_verified"]=True
    assert api.get("/api/v1/oracle/vehicles/modifications",
        params={"model_id":37773,"kind":"passenger"}).status_code==503
