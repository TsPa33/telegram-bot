"""Contract/SQL adapter tests with synthetic rows; no source or Railway DB."""
import sys,json
from pathlib import Path
from contextlib import contextmanager
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).parents[1]))
sys.path.insert(0,str(Path(__file__).parent))
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
    assert len(statements)==3
    assert all(s.startswith('CREATE TABLE IF NOT EXISTS catalogue_') for s in statements)
    with pytest.raises(ValueError):schema_statements('DROP TABLE parts;')


def test_real_export_shape_counts_without_private_data():
    from volvo_shape_fixture import fixture
    p=validate(fixture())
    assert len(p['categories'])==113 and len(p['articles'])==736
    assert len({a['supplier_id'] for a in p['articles'].values()})==175
    assert sum(bool(a['oem']) for a in p['articles'].values())==459
    assert sum(bool(a['images']) for a in p['articles'].values())==465
    assert len(p['details']['passanger_car_pds'])==434
    expected={(r['productid'],r['supplierid']) for r in p['details']['passanger_car_pds']}
    found={(r['product_id'],p['articles'][key]['supplier_id']) for r in p['categories'] for key in r['articles']}
    assert found==expected and len(found)==434
    assert p['coverage']=='partial'


def test_translation_and_pds_verification_do_not_approve_vehicle_coverage():
    from volvo_shape_fixture import fixture
    from volvo_review import review_taxonomy,review_coverage
    from volvo_contract import coverage_verified
    p=fixture();p['categories']=p['categories'][:1]
    pid=str(p['categories'][0]['product_id'])
    mapping={pid:dict(name_uk='Акумулятор',category_path=['Електрика та електроніка','Проводка та живлення','Акумулятор'],kind='part')}
    reviewed=review_taxonomy(p,mapping,'synthetic-reviewer')
    assert reviewed['taxonomy_status']=='reviewed' and reviewed['coverage']=='partial'
    assert not coverage_verified(reviewed)
    with pytest.raises(ValueError):review_coverage(reviewed,'reviewer','',True)
    approved=review_coverage(reviewed,'reviewer','SYNTHETIC independent vehicle completeness evidence',True)
    assert coverage_verified(approved)
    approved['articles'].pop(next(iter(approved['articles'])))
    with pytest.raises(ValueError):validate(approved)


def test_legacy_translation_only_complete_is_rejected():
    p=payload();p['categories']=[{'product_id':1,'articles':[]}];p['coverage']='complete_verified';p['reviewed_by']='old-translation-only';p['collection_complete']=True
    with pytest.raises(ValueError):validate(p)


def test_compact_113_plan_excludes_detailed_source_fields():
    from volvo_shape_fixture import fixture
    from volvo_contract import compact_plan,encode
    p=fixture(padded=True)
    compact=compact_plan(p,digest(p))
    assert len(encode(p))>3*1024*1024
    assert len(encode(compact))<50*1024
    assert len(compact['categories'])==113 and 'articles' not in compact and 'details' not in compact
    assert not compact['coverage_verified']
    assert all('original' not in r and 'articles' not in r for r in compact['categories'])


def test_selective_upload_ignores_stray_files_and_pins_identity_sha_status(tmp_path):
    from volvo_shape_fixture import fixture
    from volvo_vehicle_import import load_upload
    p=fixture();sha=digest(p)
    (tmp_path/'107555.json').write_text(json.dumps(dict(payload=p,sha256=sha)))
    (tmp_path/'107556.json').write_text('invalid unrelated file must not be loaded')
    assert load_upload(tmp_path,107555,sha,'partial')['sha256']==sha
    for car,expected,coverage in [(107556,sha,'partial'),(107555,'f'*64,'partial'),(107555,sha,'complete_verified')]:
        with pytest.raises(ValueError):load_upload(tmp_path,car,expected,coverage)
    p['car_id']=107556
    (tmp_path/'107555.json').write_text(json.dumps(dict(payload=p,sha256=digest(p))))
    with pytest.raises(ValueError):load_upload(tmp_path,107555,digest(p),'partial')


def test_draft_exact_113_types_only_corporate_paths_and_no_approval():
    import runpy
    root=Path(__file__).resolve().parents[2]
    draft=json.loads((root/'warehouse/docs/unified-catalogue/review/volvo-107555-taxonomy-draft.json').read_text('utf-8'))
    corporate=runpy.run_path(str(root/'warehouse/backend/app/services/catalogue_carpot_sections.py'))
    expected={s:[n for n,_ in corporate['SUBCATEGORIES'][i]] for i,s in enumerate(corporate['SECTIONS'])}
    assert json.loads((root/'catalogue/carpot_taxonomy.json').read_text('utf-8'))==expected
    assert len(draft)==113
    assert all(r['review_status']=='draft' for r in draft.values())
    assert all(r['kind'] in ('part','consumable','equipment','review') for r in draft.values())
    for row in draft.values():
        section,sub,_=row['category_path']
        if section is not None:assert section in expected
        if sub is not None:assert sub in expected[section]
    assert draft['830']['original']==draft['2055']['original'] and draft['830']['product_id']!=draft['2055']['product_id']
    assert draft['322']['kind']=='review'


def test_upload_writes_one_raw_immutable_version_and_compact_latest(monkeypatch):
    import volvo_vehicle_import as importer
    from volvo_shape_fixture import fixture
    p=fixture(padded=True);sha=digest(p)
    calls=[]
    class FakeCursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args=()):calls.append((sql,args))
    class Target:
        committed=False
        def cursor(self):return FakeCursor()
        def commit(self):self.committed=True
    target=Target()
    monkeypatch.setattr(importer,'check_space',lambda target:0)
    importer.upload_snapshot(target,dict(payload=p,sha256=sha))
    raw=[(sql,args) for sql,args in calls if 'INSERT IGNORE INTO catalogue_volvo_versions' in sql]
    latest=[(sql,args) for sql,args in calls if 'INSERT INTO catalogue_volvo_snapshots' in sql]
    assert len(raw)==len(latest)==1 and target.committed
    assert raw[0][1][0]==latest[0][1][0]==107555
    assert len(raw[0][1][2].encode())>3*1024*1024
    compact=json.loads(latest[0][1][2])
    assert compact['source_snapshot_sha']==sha and 'articles' not in compact
    assert 'ON DUPLICATE KEY UPDATE' not in raw[0][0]


def test_pinned_missing_snapshot_never_reads_latest(monkeypatch):
    monkeypatch.setenv('CATALOGUE_API_KEY','fixture-only')
    class Missing(Cursor):
        def fetchone(self):return None
    c=Missing(payload())
    class Connection:
        def cursor(self):return c
    @contextmanager
    def db():yield Connection()
    monkeypatch.setattr(catalogue_app,'db',db)
    r=TestClient(catalogue_app.app).get('/api/v1/volvo/modifications/107555/articles',params={'product_id':1,'snapshot_sha':'a'*64},headers={'X-Catalogue-Key':'fixture-only'})
    assert r.status_code==409
    assert len(c.sql)==1 and 'catalogue_volvo_versions' in c.sql[0][0]
    assert c.sql[0][1]==(107555,'a'*64)


def test_first_import_read_only_preflight_has_no_connections(tmp_path,monkeypatch,capsys):
    from volvo_shape_fixture import fixture
    import volvo_vehicle_import as importer
    p=fixture();sha=digest(p)
    (tmp_path/'107555.json').write_text(json.dumps(dict(payload=p,sha256=sha)))
    monkeypatch.setattr(importer,'connection',lambda *args:pytest.fail('Preflight must not connect to source/target'))
    monkeypatch.setattr(sys,'argv',['volvo_vehicle_import.py','--validate-upload','--car-id','107555','--expected-sha256',sha,'--expected-coverage','partial','--output',str(tmp_path)])
    importer.main()
    summary=json.loads(capsys.readouterr().out)
    assert (summary['types'],summary['articles'],summary['suppliers'])==(113,736,175)
    assert (summary['pds_pair_total'],summary['pds_pairs_matched'])==(434,434)
    assert summary['coverage']=='partial' and summary['writes']==0


def test_generic_directory_only_advertises_valid_linked_snapshots(monkeypatch):
    from volvo_contract import compact_plan
    p=payload();p.update(schema='carpot.vehicle.v1',manufacturer_id=77,car_id=900,model_id=880,model={'generation':'Source generation'})
    p['categories']=[dict(product_id=1,articles=['5:SOURCE-1'])]
    p['articles']={'5:SOURCE-1':dict(article_number='SOURCE-1',supplier_id=5,car_id=900,oem=[])}
    validate(p)
    assert compact_plan(p,'a'*64)['schema']=='carpot.vehicle.plan.v1'
    class DirectoryCursor(Cursor):
        def execute(self,sql,args):
            assert sql.lstrip().startswith('SELECT')
            self.sql.append((sql,args))
        def fetchall(self):
            return [dict(car_id=900,source_model_id=880,manufacturer_id=77,manufacturer_name='Actual source brand',model_name='Source model')]
    cursor=DirectoryCursor(p)
    class Connection:
        def cursor(self):return cursor
    @contextmanager
    def database():yield Connection()
    monkeypatch.setattr(catalogue_app,'db',database)
    monkeypatch.setattr(catalogue_app,'volvo_snapshot',lambda car:(p,digest(p)))
    monkeypatch.setenv('CATALOGUE_API_KEY','fixture-only')
    client=TestClient(catalogue_app.app)
    response=client.get('/api/v1/vehicles/directory',headers={'X-Catalogue-Key':'fixture-only'})
    assert response.status_code==200,response.text
    item=response.json()['items'][0]
    assert item['manufacturer']=='Actual source brand' and item['generation']=='Source generation'
    assert item['type_count']==1 and item['article_count']==1
    p['categories'][0]['articles']=[]
    assert client.get('/api/v1/vehicles/directory',headers={'X-Catalogue-Key':'fixture-only'}).json()['items']==[]
    assert client.get('/api/v1/vehicles/directory').status_code==401
