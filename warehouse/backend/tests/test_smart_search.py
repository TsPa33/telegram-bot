"""Controlled real PostgreSQL records, not mocked result sets or provider data."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from conftest import signup
from app.main import app
from app.db import engine
from app.search.normalize import normalize,identifier

@pytest.fixture
def search_data(logged):
    c=logged
    def post(path,data):
        r=c.post('/api/v1'+path,json=data);assert r.status_code in (200,201),r.text;return r.json()
    volvo=post('/vehicles',{'manufacturer':'Volvo','model':'XC60','year':2016,'generation':'I'})
    other=post('/vehicles',{'manufacturer':'Volvo','model':'XC60','year':2018,'generation':'II'})
    bmw=post('/vehicles',{'manufacturer':'BMW','model':'X3','year':2014})
    lacetti=post('/vehicles',{'manufacturer':'Chevrolet','model':'Lacetti','year':2010})
    rows={}
    for name,car,extra,qty in [
      ('Блок керування двигуном',volvo,{},2),('Блок керування двигуном BMW',bmw,{},1),
      ('Блок керування АКПП',volvo,{},1),('Задній ліхтар правий',volvo,{},1),('Задній ліхтар лівий',volvo,{},1),
      ('Передня ліва фара',volvo,{},1),('Передні ліві двері',volvo,{},1),('Передні праві двері',volvo,{},1),
      ('Автоматична коробка передач',volvo,{},1),('Механічна коробка передач',volvo,{},1),
      ('Радіатор охолодження',volvo,{},1),('Бампер передній',volvo,{'oem_number':'ABC-123','article_number':'ART-77-09'},1),
      ('Бампер новішого донора',other,{},1),('Фара передня ліва Lacetti',lacetti,{},1),
      ('Капот',volvo,{},1),('Кардан',volvo,{},0),('Генератор',volvo,{},1),('Фара зарезервована',volvo,{},1)
    ]:
        p=post('/parts',{'name':name,'vehicle_id':car['id'],'selling_price':'123.45','currency':'USD',**extra})
        if qty:post('/parts/'+p['id']+'/operations',{'type':'receipt','quantity':qty,'reason':'Smart local fixture'})
        rows[name]=p
    post('/parts/'+rows['Фара зарезервована']['id']+'/operations',{'type':'reserve','quantity':1,'reason':'Local reservation'})
    return c,rows,volvo

def find(c,q,**params):
    r=c.get('/api/v1/smart-search/parts',params={'q':q,**params});assert r.status_code==200,r.text;return r.json()

def names(c,q,**params):return {p['name'] for p in find(c,q,**params)['items']}

@pytest.mark.parametrize('q,expected',[
 ('мозги мотора','Блок керування двигуном'),('мозги мотора XC60','Блок керування двигуном'),
 ('правий задній стоп','Задній ліхтар правий'),('лівий задній стоп','Задній ліхтар лівий'),
 ('передня ліва дверка','Передні ліві двері'),('коробка автомат','Автоматична коробка передач'),
 ('коробка механіка','Механічна коробка передач'),('радік вольво','Радіатор охолодження'),
 ('бампер хс60 2016','Бампер передній'),('ABC-123','Бампер передній'),('ART-77-09','Бампер передній'),
 ('капотт','Капот'),('радиатор','Радіатор охолодження'),('радіатор','Радіатор охолодження'),
 ('radik volvo','Радіатор охолодження'),('мотора XC60 мозги','Блок керування двигуном'),
 ('Фара на Лачетті','Фара передня ліва Lacetti')])
def test_required_queries(search_data,q,expected):
    c,rows,_=search_data;result=find(c,q);assert rows[expected]['id'] in {p['id'] for p in result['items']},result
    assert all(p['account_id']==rows[expected]['account_id'] and p['currency']=='USD' for p in result['items'])


def test_directions_unknown_ambiguity_stock_and_filters(search_data):
    c,rows,v=search_data
    assert names(c,'правий задній стоп')=={'Задній ліхтар правий'}
    assert names(c,'лівий задній стоп')=={'Задній ліхтар лівий'}
    assert names(c,'передня ліва дверка')=={'Передні ліві двері'}
    assert 'Механічна коробка передач' not in names(c,'коробка автомат')
    assert not names(c,'чарівнийнеіснуючийпристрій')
    assert find(c,'стоп')['clarification'] and find(c,'ліва права фара')['clarification']
    assert 'Кардан' not in names(c,'кардан',in_stock=True)
    assert 'Кардан' in names(c,'кардан',in_stock=False)
    assert {'Капот','Кардан'} <= names(c,'ка',in_stock=False)
    assert 'Фара зарезервована' not in names(c,'фара',in_stock=True)
    assert names(c,'бампер хс60 2016')=={'Бампер передній'}
    assert 'Бампер новішого донора' in names(c,'бампер XC60 II')
    assert not names(c,'бампер XC60 III')
    assert names(c,'бампер',vehicle_id=v['id'])=={'Бампер передній'}
    assert not names(c,'бампер',manufacturer='BMW')
    # Search never changes the stock ledger or inventory.
    before=c.get('/api/v1/audit').json()['total'];result=find(c,'мозги мотора');assert c.get('/api/v1/audit').json()['total']==before
    assert 'мозги' in result['items'][0]['match_explanation'] and 'mozgy' not in result['items'][0]['match_explanation']


def test_ranking_pagination_codes_and_tenant(search_data):
    c,rows,v=search_data
    assert find(c,'abc123')['items'][0]['id']==rows['Бампер передній']['id']
    assert find(c,'art7709')['items'][0]['article_number']=='ART-77-09'
    full=find(c,'',limit=100)['items'];pages=[find(c,'',limit=1,offset=i)['items'][0]['id'] for i in range(len(full))]
    assert pages==[p['id'] for p in full] and len(set(pages))==len(pages)
    with TestClient(app) as other:
        assert other.get('/api/v1/smart-search/parts').status_code==401
        signup(other,'other-search@example.test')
        assert find(other,'ABC-123')['total']==0
        assert find(other,'',vehicle_id=v['id'])['total']==0
    for params in ({'q':'x'*161},{'q':' '.join(['word']*13)},{'limit':101},{'offset':100001}):
        assert c.get('/api/v1/smart-search/parts',params=params).status_code==422
    assert not names(c,"'; DROP TABLE parts; --")


def test_normalization_sql_parity_and_contracts(logged):
    samples=['  ФАРА, лІва!  ',"об’єкт об'ект",'Радиатор XC60','АКПП 2.4 D5','щ ґ є ї й ё ь ъ','ABC-123','ｅｃｕ','1,9 TDI','Škoda Citroën','й і и ї']
    with engine().connect() as db:
        for value in samples:
            assert db.scalar(text('SELECT warehouse_search_text(:v)'),{'v':value})==normalize(value)
            assert db.scalar(text('SELECT warehouse_search_code(:v)'),{'v':value})==identifier(value)
    for path,contract in [('sales-workspace',5),('orders',6),('workshop',7),('smart-search',8)]:
        r=logged.get('/api/v1/'+path+'/readiness');assert r.status_code==200,r.text;assert r.json()['contract_version']==contract
    assert logged.get('/api/v1/smart-search/parts').status_code==200
    assert logged.get('/api/v1/parts/smart-search').status_code==404 # not shadowing the old Part route


def test_migration_preserves_inventory_audit_and_readiness(search_data):
    from subprocess import run
    import sys
    c,_,_=search_data
    with engine().connect() as db:
        parts=db.execute(text('SELECT row_to_json(p) FROM parts p ORDER BY id')).scalars().all()
        audit=db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()
    run([sys.executable,'-m','alembic','downgrade','d86f21a90b34'],check=True)
    assert c.get('/api/v1/smart-search/readiness').status_code==503
    run([sys.executable,'-m','alembic','upgrade','head'],check=True)
    with engine().connect() as db:
        assert db.execute(text('SELECT row_to_json(p) FROM parts p ORDER BY id')).scalars().all()==parts
        assert db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()==audit
    run([sys.executable,'-m','alembic','check'],check=True)
    assert c.get('/api/v1/smart-search/readiness').json()['required_revision']=='a73e05b9c842'
    with engine().begin() as db:db.execute(text('DROP INDEX ix_parts_smart_trgm'))
    assert c.get('/api/v1/smart-search/readiness').status_code==503
    with engine().begin() as db:db.execute(text("CREATE INDEX ix_parts_smart_trgm ON parts USING gin (warehouse_search_text(name) gin_trgm_ops) WHERE NOT archived"))


def test_only_recorded_powertrain_and_no_inferred_generation(search_data):
    c,rows,v=search_data
    assert c.patch('/api/v1/vehicles/'+v['id']+'/powertrain',json={'engine':'2.4 D5 дизель','transmission':'АКПП'}).status_code==200
    r=c.post('/api/v1/parts',json={'vehicle_id':v['id'],'name':'Коробка передач'});assert r.status_code==201
    assert 'Коробка передач' in names(c,'коробка автомат')
    assert 'Коробка передач' in names(c,'АКПП')
    assert 'Блок керування двигуном' in names(c,'мозги мотора D5')
    assert 'Коробка передач' not in names(c,'коробка механіка')
    assert 'Блок керування двигуном' in names(c,'мозги мотора дизель 2.4')
    assert not names(c,'мозги мотора бензин')
    # Roman generation is explicit, never guessed from year or Part.name.
    c.post('/api/v1/parts',json={'vehicle_id':v['id'],'name':'Бампер III'})
    assert not names(c,'бампер XC60 III')


def test_real_donor_diacritics_and_engine_precision(search_data):
    c,_,_=search_data
    v=c.post('/api/v1/vehicles',json={'manufacturer':'Škoda','model':'Octavia','year':2016}).json()
    p=c.post('/api/v1/parts',json={'vehicle_id':v['id'],'name':'Фара'}).json()
    assert p['id'] in {r['id'] for r in find(c,'фара шкода')['items']}


def test_multiword_actual_brand_is_not_a_guessed_alias(logged):
    c=logged
    for brand in ['Land Rover','Mercedes-Benz']:
        v=c.post('/api/v1/vehicles',json={'manufacturer':brand,'model':'Test model','year':2016}).json()
        p=c.post('/api/v1/parts',json={'vehicle_id':v['id'],'name':'Радіатор'}).json()
        assert p['id'] in {r['id'] for r in find(c,'радік '+brand)['items']}


def test_exact_identifier_wins_over_model_or_year_interpretation(search_data):
    c,_,v=search_data
    for sku in ['X3','A-2016','STOP']:
        p=c.post('/api/v1/parts',json={'name':'Окрема деталь','vehicle_id':v['id'],'oem_number':sku}).json()
        result=find(c,sku)
        assert result['total']==1 and result['items'][0]['id']==p['id']
        assert result['items'][0]['relevance']==1000


def test_steering_type_and_turbo_are_not_universal_aliases(logged):
    c=logged
    rows={}
    for name in ['Кермовий механізм рейкового типу','Кермовий черв’ячний механізм','Кермовий механізм','Турбокомпресор','Турбодвигун']:
        rows[name]=c.post('/api/v1/parts',json={'name':name}).json()
    assert names(c,'рульова рейка')=={'Кермовий механізм рейкового типу'}
    assert names(c,'турбіна')=={'Турбокомпресор'}


def test_ranking_search_is_not_limited_to_first_50_inventory_records(search_data):
    from sqlalchemy import insert
    from app.models import Part
    c,_,v=search_data
    old=c.post('/api/v1/parts',json={'vehicle_id':v['id'],'name':'Давно облікована деталь','oem_number':'OLD-RANK-57'}).json()
    with engine().begin() as db:
        db.execute(insert(Part),[{'account_id':old['account_id'],'vehicle_id':v['id'],'name':f'Новіша деталь {i}'} for i in range(1000)])
    assert old['id'] not in {p['id'] for p in c.get('/api/v1/parts',params={'limit':50}).json()['items']}
    result=find(c,'OLD-RANK-57')
    assert result['total']==1 and result['items'][0]['id']==old['id']


@pytest.mark.parametrize('index,ddl',[
    ('ix_vehicle_smart_brand', 'CREATE INDEX ix_vehicle_smart_brand ON vehicles (account_id,warehouse_search_text(manufacturer))'),
    ('ix_vehicle_smart_model', "CREATE INDEX ix_vehicle_smart_model ON vehicles USING gin (to_tsvector('simple',warehouse_search_text(model)))"),
])
def test_readiness_requires_vehicle_indexes(logged,index,ddl):
    try:
        with engine().begin() as db:db.execute(text('DROP INDEX '+index))
        assert logged.get('/api/v1/smart-search/readiness').status_code==503
    finally:
        with engine().begin() as db:db.execute(text(ddl))
    assert logged.get('/api/v1/smart-search/readiness').status_code==200


@pytest.mark.parametrize('failure',['late_index_conflict','table_lock'])
def test_failed_upgrade_is_transactional_and_retryable(search_data,failure):
    import sys
    from subprocess import run
    c,_,_=search_data
    def alembic(*args):return run([sys.executable,'-m','alembic',*args],capture_output=True,text=True)
    with engine().connect() as db:
        before=db.execute(text('SELECT row_to_json(p) FROM parts p ORDER BY id')).scalars().all()
        audit=db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()
    assert alembic('downgrade','d86f21a90b34').returncode==0
    # Compare every column that exists at the intentionally old revision.
    # Stage3B metadata is additive and absent until the final upgrade.
    new_fields={'assortment_enabled','inventory_origin','quantity_basis','physical_location_kind','canonical_placement_id','activation_operation_id','color_name','paint_code'}
    before=[{k:v for k,v in row.items() if k not in new_fields} for row in before]
    blocker=None
    try:
        if failure=='late_index_conflict':
            with engine().begin() as db:db.execute(text('CREATE INDEX ix_vehicle_smart_brand ON vehicles (id)'))
        else:
            blocker=engine().connect();blocker.execute(text('LOCK TABLE parts IN ACCESS EXCLUSIVE MODE'))
        result=alembic('upgrade','head')
        assert result.returncode!=0
        assert ('already exists' if failure=='late_index_conflict' else 'lock timeout') in result.stderr
    finally:
        if blocker is not None:blocker.rollback();blocker.close()
        if failure=='late_index_conflict':
            with engine().begin() as db:db.execute(text('DROP INDEX IF EXISTS ix_vehicle_smart_brand'))
    with engine().connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='d86f21a90b34'
        assert db.scalar(text("SELECT to_regprocedure('warehouse_search_text(text)')")) is None
        assert db.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'ix_%smart_%'"))==0
        assert db.execute(text('SELECT row_to_json(p) FROM parts p ORDER BY id')).scalars().all()==before
        assert db.execute(text('SELECT row_to_json(o) FROM operations o ORDER BY id')).scalars().all()==audit
    assert c.get('/api/v1/smart-search/readiness').status_code==503
    assert alembic('upgrade','head').returncode==0
    assert alembic('upgrade','head').returncode==0 # Alembic head is a no-op on retry.
    assert c.get('/api/v1/smart-search/readiness').status_code==200
