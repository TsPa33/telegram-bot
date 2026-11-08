"""Contract/SQL adapter tests with synthetic rows; no source or Railway DB."""
import sys,json
from pathlib import Path
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
from volvo_contract import validate,digest
import app as catalogue_app
from volvo_vehicle_import import collect


def payload():
    return dict(schema='carpot.volvo.v1',manufacturer_id=120,car_id=107555,model_id=13084,
        coverage='partial',observed_at='2026-11-08T00:00:00Z',categories=[],articles={},modification={'description':'T6 AWD'})


def test_contract_cannot_publish_partial_as_complete():
    p=payload();validate(p);p['coverage']='complete_verified'
    with pytest.raises(ValueError):validate(p)


def test_contract_duplicate_product_ids():
    p=payload();p['categories']=[{'product_id':1},{'product_id':1}]
    with pytest.raises(ValueError):validate(p)


class Cursor:
    def __init__(self,data):self.data=data;self.sql=[]
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def execute(self,sql,args):self.sql.append((sql,args))
    def fetchone(self):return {'payload':json.dumps(self.data),'sha256':digest(self.data)}
    def fetchall(self):return []


def test_api_auth_snapshot_and_photo_metadata(monkeypatch):
    monkeypatch.setenv('CATALOGUE_API_KEY','fixture-only')
    c=Cursor(payload())
    class Connection:
        def cursor(self):return c
    @contextmanager
    def db():yield Connection()
    monkeypatch.setattr(catalogue_app,'db',db)
    client=TestClient(catalogue_app.app)
    assert client.get('/api/v1/volvo/modifications/107555/plan').status_code==401
    r=client.get('/api/v1/volvo/modifications/107555/plan',headers={'X-Catalogue-Key':'fixture-only'})
    assert r.status_code==200
    assert r.json()['payload']['car_id']==107555
    # The server's lookup is bound to an exact ID, no text inference.
    assert c.sql[-1][1]==(107555,)
    assert all('SELECT ' in sql for sql,_ in c.sql)


def test_snapshot_wrong_identity_rejected(monkeypatch):
    monkeypatch.setenv('CATALOGUE_API_KEY','fixture-only')
    c=Cursor(payload())
    class Connection:
        def cursor(self):return c
    @contextmanager
    def db():yield Connection()
    monkeypatch.setattr(catalogue_app,'db',db)
    assert TestClient(catalogue_app.app).get('/api/v1/volvo/modifications/107556/plan',headers={'X-Catalogue-Key':'fixture-only'}).status_code==503


def test_import_source_only_selects_and_preserves_oem_crosses(monkeypatch):
    import volvo_vehicle_import as importer
    calls=[]
    def read(conn,sql,args=()):
        calls.append(sql)
        assert sql.lstrip().startswith('SELECT')
        if 'SELECT DISTINCT productid' in sql:
            return [dict(productid=106,supplierid=2,datasupplierarticlenumber='SYNTHETIC')] if args[1:]==(0,0,'') else []
        if 'FROM article_oe' in sql:return [{'OENbr':'OEM-CROSS'}]
        if 'FROM article_images' in sql:return [{'PictureName':'2_E325.JPG'}]
        return []
    monkeypatch.setattr(importer,'read',read)
    p=collect(object(),{'id':107555},{'id':13084},{})
    assert p['coverage']=='partial' and p['collection_complete'] is True
    assert p['articles']['2:SYNTHETIC']['oem']==[{'OENbr':'OEM-CROSS'}]
    assert p['articles']['2:SYNTHETIC']['image_status']=='metadata_only'
    assert 'photo_url' not in p['articles']['2:SYNTHETIC']
    assert any('linkagetypeid=2' in s for s in calls)


def test_target_schema_additive_only_and_handles_comment_semicolon():
    from volvo_target import schema_statements
    statements=schema_statements((Path(__file__).parents[1]/'volvo_integration.sql').read_text())
    assert len(statements)==2
    assert all(s.startswith('CREATE TABLE IF NOT EXISTS catalogue_') for s in statements)
    with pytest.raises(ValueError):schema_statements('DROP TABLE parts;')
