from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import control_directory as source
from app.services.control_transport import signature
import time

def test_directory_requires_staging_opt_in_and_signed_exact_query(monkeypatch):
    key = "test-key-" * 8
    monkeypatch.setenv("WAREHOUSE_CONTROL_DIRECTORY_KEY", key)
    monkeypatch.setenv("WAREHOUSE_ENV", "staging")
    app = FastAPI()
    app.include_router(source.router)
    with TestClient(app) as client:
        path = "/internal/control/warehouse-directory"
        assert client.get(path).status_code == 404
        monkeypatch.setenv("WAREHOUSE_CONTROL_DIRECTORY_ENABLED", "true")
        assert client.get(path).status_code == 401
        stamp = str(int(time.time()))
        headers = {"X-Control-Stamp":stamp,"X-Control-Signature":signature(key,stamp,"",20)}
        assert client.get(path,params={"limit":21},headers=headers).status_code == 401
        assert client.get(path,params={"cursor":"other"},headers=headers).status_code == 401
        class FakeSession:
            def __init__(self,*a): pass
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def execute(self,sql): statements.append(str(sql))
        statements=[]
        monkeypatch.setattr(source,"engine",lambda:None)
        monkeypatch.setattr(source,"Session",FakeSession)
        monkeypatch.setattr(source,"read_batch",lambda db,cursor,limit,env: ([{"workspace_id":"test"}],None))
        result=client.get(path,headers=headers)
        assert result.status_code==200 and result.json()["environment"]=="staging"
        assert statements[0]=="SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        monkeypatch.setenv("WAREHOUSE_ENV","production")
        assert client.get(path,headers=headers).status_code==404
