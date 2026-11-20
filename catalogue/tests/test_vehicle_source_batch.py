"""Offline source/target contracts only. Fixtures are synthetic, not live imports."""
import json
import sys
from copy import deepcopy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vehicle_source_batch as batch
import volvo_vehicle_import as collector
from volvo_contract import digest,encode


def payload():
    return dict(schema='carpot.vehicle.v1',manufacturer_id=77,model_id=88,car_id=99,
        manufacturer={'id':77,'description':'Synthetic maker'},model={'id':88,'manufacturerid':77,'description':'Synthetic model'},
        modification={'id':99,'modelid':88},observed_at='2026-11-11T00:00:00+00:00',
        categories=[dict(product_id=1,original=[dict(id=1,description='Test starter')],articles=['5:TEST'],name_uk='Стартер',kind='part',category_path=['Електрика та електроніка','Стартери та генератори','Стартер'],mapping_reviewed_by='synthetic fixture')],
        articles={'5:TEST':dict(supplier_id=5,article_number='TEST',car_id=99)},
        details={'passanger_car_pds':[dict(productid=1,supplierid=5),dict(productid=2,supplierid=6)]},
        collection_complete=True,coverage='partial',taxonomy_status='reviewed')


def test_export_resume_hashes_and_pds_candidates(tmp_path,monkeypatch):
    queries=[];calls=[]
    def read(db,sql,args=()):
        queries.append(sql);assert sql.startswith('SELECT ')
        if 'information_schema' in sql:return [dict(TABLE_NAME='passenger_cars')]
        if 'FROM passenger_cars' in sql:return [dict(id=99,modelid=88)]
        if 'FROM models' in sql:return [dict(id=88,manufacturerid=77)]
        if 'FROM manufacturers' in sql:return [dict(id=77,description='Synthetic maker',ispassengercar=True)]
        if 'FROM prd' in sql:return [dict(id=1,description='Test starter')] if args==(0,) else []
        raise AssertionError(sql)
    def collect(*args,**kwargs):calls.append(kwargs);return payload()
    monkeypatch.setattr(batch,'read',read);monkeypatch.setattr(batch,'collect',collect)
    first=batch.export(None,tmp_path,[99],[],1)
    assert first['modifications'][0]['pds_only_product_ids']==[2]
    assert first['modifications'][0]['pds_only_fitment']=='needs_review'
    batch.export(None,tmp_path,[99],[],1)
    with pytest.raises(ValueError,match='Checkpoint request changed'):
        batch.export(None,tmp_path,[99],[],1,graph_only=True)
    assert len(calls)==1 and calls[0]['manufacturer_id']==77
    sha=batch.file_sha(tmp_path/'manifest.json')
    envelopes=batch.validate_batch(tmp_path,sha)
    assert envelopes[0]['payload']['car_id']==99
    with pytest.raises(ValueError):batch.export(None,tmp_path,[100],[],1)
    (tmp_path/'99.json').write_text('{}')
    with pytest.raises(ValueError):batch.validate_batch(tmp_path,sha)


def test_passenger_manufacturer_selects_only_correct_role():
    rows=[
        dict(id=120,description='VOLVO',ispassengercar='False',isaxle='True'),
        dict(id=120,description='VOLVO',ispassengercar='True',iscommercialvehicle='True'),
        dict(id=120,description='VOLVO',ispassengercar='False',isengine='True'),
    ]
    assert batch.select_passenger_manufacturer(rows,120) is rows[1]
    assert batch.select_passenger_manufacturer([dict(id=121,ispassengercar=1),dict(id=121,ispassengercar=0)],121)['ispassengercar']==1


@pytest.mark.parametrize('rows',[[],[dict(id=120,ispassengercar='False')],
    [dict(id=120,ispassengercar=True),dict(id=120,ispassengercar='True')]])
def test_passenger_manufacturer_rejects_missing_or_ambiguous_role(rows):
    with pytest.raises(ValueError,match='expected exactly one ispassengercar=True row'):
        batch.select_passenger_manufacturer(rows,120)


def test_manifest_path_traversal_and_identity(tmp_path):
    (tmp_path/'manifest.json').write_bytes(encode(dict(schema='carpot.source.batch.v1',complete=True,files={'../secret.json':'0'*64},modifications=[])))
    with pytest.raises(ValueError,match='path'):batch.validate_batch(tmp_path,batch.file_sha(tmp_path/'manifest.json'))


def test_upload_replay_conflict_before_any_writes(monkeypatch):
    p=payload();envelope=dict(payload=p,sha256=digest(p))
    monkeypatch.setattr(batch,'inventory',lambda target:[dict(car_id=99,model_id=88,sha256=envelope['sha256'])])
    assert batch.upload(None,[envelope])==dict(uploaded=0,skipped=1)
    monkeypatch.setattr(batch,'inventory',lambda target:[dict(car_id=99,model_id=88,sha256='0'*64)])
    with pytest.raises(ValueError,match='differs'):batch.upload(None,[envelope])


def test_collector_oem_uses_exact_manufacturer(monkeypatch):
    queries=[]
    def read(db,sql,args=()):
        assert sql.startswith('SELECT ');queries.append((sql,args))
        if sql.startswith('SELECT DISTINCT'):
            return [dict(productid=1,supplierid=5,datasupplierarticlenumber='TEST')] if args[1:]==(0,0,'') else []
        if 'FROM prd ' in sql:return [dict(id=1,description='Test starter')]
        return []
    monkeypatch.setattr(collector,'read',read)
    p=collector.collect(None,dict(id=99),dict(id=88),{},manufacturer_id=77)
    assert p['schema']=='carpot.vehicle.v1' and p['manufacturer_id']==77
    oem=next((sql,args) for sql,args in queries if 'FROM article_oe ' in sql)
    assert oem[1][-2]==77 and 'manufacturerId=120' not in oem[0]


def test_graph_only_preserves_exact_links_without_per_article_enrichment(monkeypatch):
    queries=[]
    def read(db,sql,args=()):
        queries.append(sql)
        if sql.startswith('SELECT DISTINCT'):
            if args[1:] == (0,0,''):
                return [dict(productid=1,supplierid=5,datasupplierarticlenumber='TEST'),
                        dict(productid=2,supplierid=5,datasupplierarticlenumber='TEST')]
            return []
        if 'FROM prd ' in sql:
            return [dict(id=args[0],description='Synthetic source type')]
        if 'FROM passanger_car_' in sql:
            return []
        raise AssertionError('Graph-only mode must not fetch individual article enrichment: '+sql)
    monkeypatch.setattr(collector,'read',read)
    p=collector.collect(None,dict(id=99),dict(id=88),{},manufacturer_id=77,graph_only=True)
    assert p['schema']=='carpot.vehicle.v1'
    assert p['source_scope']=='modification_prd_article_graph'
    assert p['image_status']=='not_exported'
    assert len(p['articles'])==1 and p['articles']['5:TEST']['enrichment_status']=='not_exported'
    assert {r['product_id'] for r in p['categories']}=={1,2}
    assert all(r['articles']==['5:TEST'] for r in p['categories'])
    assert all('FROM article_' not in q for q in queries if not q.startswith('SELECT DISTINCT'))


def test_repeated_article_metadata_counted_once(monkeypatch):
    large='X'*(5*1024*1024)
    def read(db,sql,args=()):
        if sql.startswith('SELECT DISTINCT'):
            if args[1:]==(0,0,''):
                return [dict(productid=1,supplierid=5,datasupplierarticlenumber='TEST'),
                        dict(productid=2,supplierid=5,datasupplierarticlenumber='TEST')]
            return []
        if 'FROM article_attributes' in sql:return [dict(raw_metadata=large)]
        if 'FROM prd ' in sql:return [dict(id=args[0],description='Synthetic type')]
        return []
    monkeypatch.setattr(collector,'read',read)
    p=collector.collect(None,dict(id=99),dict(id=88),{},manufacturer_id=77)
    assert len(p['articles'])==1
    assert len(p['categories'])==2
    assert len(encode(p)) < 8*1024*1024


def test_offline_review_keeps_original_and_coverage(tmp_path,monkeypatch):
    original=tmp_path/'original';original.mkdir()
    p=payload();p['categories'][0]['original']=[dict(id=1,description='Test starter')]
    raw=dict(payload=p,sha256=digest(p))
    batch.atomic(original/'99.json',raw);batch.atomic(original/'prd.json',p['categories'][0]['original'])
    batch.atomic(original/'manifest.json',dict(schema='carpot.source.batch.v1',complete=True,files={name:batch.file_sha(original/name) for name in ('99.json','prd.json')},modifications=[batch.relation_summary(p)]))
    sha=batch.file_sha(original/'manifest.json')
    fields=('id','assemblygroupdescription','description','normalizeddescription','usagedescription')
    entry=dict(source_sha=digest({k:p['categories'][0]['original'][0].get(k) for k in fields}),name_uk='Стартер',kind='part',category_path=p['categories'][0]['category_path'])
    result=batch.review_batch(original,sha,{'1':entry},'Synthetic reviewer',tmp_path/'reviewed')
    reviewed=batch.validate_batch(tmp_path/'reviewed',result['manifest_sha256'])[0]['payload']
    assert reviewed['coverage']=='partial' and reviewed['categories'][0]['product_id']==1
    assert batch.file_sha(original/'manifest.json')==sha
    with pytest.raises(ValueError,match='checksum'):
        batch.review_batch(original,sha,{'1':{**entry,'source_sha':'0'*64}},'Synthetic reviewer',tmp_path/'bad')


@pytest.mark.parametrize('fail',[False,True])
def test_generic_target_transaction_and_rollback(monkeypatch,fail):
    p=payload();envelope=dict(payload=p,sha256=digest(p));calls=[]
    monkeypatch.setattr(batch,'inventory',lambda target:[])
    monkeypatch.setattr(collector,'check_space',lambda target:0)
    class Cursor:
        sql=''
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,args=()):
            self.sql=sql;calls.append((sql,args))
            if 'catalogue_manufacturers (' in sql:assert 'full_name_source' in sql
            if 'catalogue_models (' in sql:assert 'production_interval' in sql
            if fail and 'INSERT INTO catalogue_volvo_snapshots' in sql:raise RuntimeError('Synthetic write failure')
        def fetchone(self):return {'manufacturer_id':77} if 'SELECT manufacturer_id' in self.sql else None
    class Target:
        commits=0;rollbacks=0
        def cursor(self):return Cursor()
        def commit(self):self.commits+=1
        def rollback(self):self.rollbacks+=1
    target=Target()
    if fail:
        with pytest.raises(RuntimeError):batch.upload(target,[envelope])
        assert target.commits==0 and target.rollbacks==1
    else:
        assert batch.upload(target,[envelope])==dict(uploaded=1,skipped=0)
        assert target.commits==1 and target.rollbacks==0
        assert any('INSERT IGNORE INTO catalogue_volvo_versions' in sql for sql,args in calls)


def test_passenger_discovery_advances_cursor_without_guessing_missing_links(monkeypatch):
    calls=[]
    def fake_read(db,sql,args=()):
        calls.append((sql,args))
        if 'information_schema.TABLES' in sql:
            return [{'TABLE_NAME':'passanger_cars'}]
        if 'FROM passanger_cars WHERE id>' in sql:
            return [{'id':12},{'id':20},{'id':27}] if args[0]==10 else []
        if 'FROM article_links WHERE linkageid=' in sql:
            return [{'productid':1}] if args[0] in (12,27) else []
        raise AssertionError(sql)
    monkeypatch.setattr(batch,'read',fake_read)
    result=batch.discover_passenger(None,10,3)
    assert result['linked_ids']==[12,27]
    assert result['next_after_id']==27
    assert result['scanned']==3 and not result['complete']
    last=batch.discover_passenger(None,27,3)
    assert last['complete'] and last['linked_ids']==[]
    assert all('SELECT ' in sql for sql,_ in calls)
    with pytest.raises(ValueError):batch.discover_passenger(None,-1,3)


def test_oem_export_can_omit_full_prd_dump_per_modification(tmp_path,monkeypatch):
    seen=[]
    def fake_read(db,sql,args=()):
        seen.append(sql)
        if 'information_schema.TABLES' in sql:return [{'TABLE_NAME':'passanger_cars'}]
        if 'FROM passanger_cars' in sql:return [{'id':99,'modelid':88}]
        if 'FROM models' in sql:return [{'id':88,'manufacturerid':77}]
        if 'FROM manufacturers' in sql:return [{'id':77,'description':'Synthetic maker','ispassengercar':True}]
        if 'FROM prd' in sql:raise AssertionError('Must not scan all PRD for every donor')
        raise AssertionError(sql)
    def fake_collect(*args,**kwargs):return payload()
    def fake_attach(source,p):
        p['source_scope']='passenger_prd_article_oem'
    monkeypatch.setattr(batch,'read',fake_read)
    monkeypatch.setattr(batch,'collect',fake_collect)
    monkeypatch.setattr(batch,'attach_source_oems',fake_attach)
    batch.export(None,tmp_path,[99],[],1,graph_only=True,with_oem=True,omit_prd_export=True)
    assert not (tmp_path/'prd.json').exists()
    assert batch.validate_batch(tmp_path,batch.file_sha(tmp_path/'manifest.json'))[0]['payload']['car_id']==99
    assert all('FROM prd' not in sql for sql in seen)


def test_model_scoped_passenger_oem_discovery_uses_indexed_modelid_and_keeps_fitment_gate(monkeypatch):
    """Model grouping finds 2017+ XC60 variants, but an article link is still required."""
    calls=[]
    def fake_read(db,sql,args=()):
        calls.append((sql,args))
        if 'information_schema.TABLES' in sql:return [{'TABLE_NAME':'passanger_cars'}]
        if 'FROM passanger_cars WHERE modelid=' in sql:
            assert args==(37773,126478,4)
            return [{'id':126479},{'id':126480},{'id':126481}]
        if 'FROM article_links WHERE linkageid=' in sql:
            return [{'productid':7}] if args[0] in (126480,126481) else []
        raise AssertionError(sql)
    monkeypatch.setattr(batch,'read',fake_read)
    result=batch.discover_passenger(None,126478,4,model_id=37773)
    assert result['linked_ids']==[126480,126481]
    assert result['model_id']==37773
    assert result['next_after_id']==126481
    assert result['complete'] is True
    assert any('WHERE modelid=%s AND id>%s' in sql for sql,_ in calls)
    with pytest.raises(ValueError):batch.discover_passenger(None,0,4,model_id=-1)
