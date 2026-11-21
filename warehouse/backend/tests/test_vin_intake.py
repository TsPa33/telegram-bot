"""Both requested VINs use declared fixtures here, never claimed as live decoding."""
from copy import deepcopy
import pytest
from app.services import vin_lookup

@pytest.fixture(autouse=True)
def fresh_vin_cache():
    vin_lookup.clear_cache()
    yield
    vin_lookup.clear_cache()


VINS=['YV4L12RK6N1970668','YV4A22PK2G1092943']

def values(vin):
    return dict(manufacturer='Volvo',model='Synthetic VIN QA',year=2020,vin=vin,drive_type='AWD',engine='Synthetic engine',engine_code='TEST-CODE',
        vin_details=dict(characteristics={'body_class':'Synthetic body','engine_power_kw':'123','doors':'5','transmission_code':'TEST-GEAR','generation':'Synthetic generation'},decoded={'engine_power_kw':'123'},source='offline_fixture',observed_at='2026-11-11T00:00:00Z'))

@pytest.mark.parametrize('vin',VINS)
def test_all_characteristics_persist_and_duplicate_is_blocked(logged,vin):
    data=values(vin);r=logged.post('/api/v1/vehicles',json=data);assert r.status_code==201,r.text
    saved=r.json();loaded=logged.get('/api/v1/vehicles/'+saved['id']).json()
    assert loaded['vin']==vin and loaded['engine_code']=='TEST-CODE'
    assert loaded['vin_details']['characteristics']==data['vin_details']['characteristics']
    assert loaded['vin_details']['decoded']==data['vin_details']['decoded']
    assert loaded['vin_details']['trust']=='user_confirmed_reported_not_factory_verified'
    again=logged.post('/api/v1/vehicles',json=data);assert again.status_code==409
    assert again.json()['detail']['vehicle_id']==saved['id']
    assert logged.get('/api/v1/parts').json()['total']==0


def test_update_cannot_duplicate_and_preserves_snapshot(logged):
    a=logged.post('/api/v1/vehicles',json=values(VINS[0])).json()
    b=logged.post('/api/v1/vehicles',json=values(VINS[1])).json()
    assert logged.put('/api/v1/vehicles/'+b['id'],json={**values(VINS[0])}).status_code==409
    simple={k:a[k] for k in ('manufacturer','model','year','vin')}
    assert logged.put('/api/v1/vehicles/'+a['id'],json=simple).json()['vin_details']==a['vin_details']


def test_unavailable_decoder_manual_and_invalid_vin(logged,monkeypatch):
    def unavailable(*a,**k):raise OSError('offline fixture')
    monkeypatch.setattr(vin_lookup,'urlopen',unavailable)
    monkeypatch.setattr('app.services.vin_freevindecoder.decode_page',lambda v:None)
    r=logged.get('/api/v1/vehicles/vin/decode?vin='+VINS[0]);assert r.status_code==200
    assert r.json()['vehicle']=={} and not r.json()['live_data_received']
    assert logged.get('/api/v1/vehicles/vin/decode?vin=I2345678901234567').status_code==422
    assert logged.post('/api/v1/vehicles',json={'manufacturer':'Manual','model':'Unknown','year':2020}).status_code==201


def test_free_provider_fallback_when_primary_unavailable(logged,monkeypatch):
    monkeypatch.setattr(vin_lookup,'urlopen',lambda *a,**k:(_ for _ in ()).throw(OSError()))
    monkeypatch.setattr('app.services.vin_freevindecoder.decode_page',lambda v:{'manufacturer':'Fixture','model':'Fixture','year':2020,'drive_type':'AWD'})
    r=logged.get('/api/v1/vehicles/vin/decode?vin='+VINS[1]).json()
    assert r['vehicle']['model']=='Fixture' and r['source']=='FreeVINDecoder'
    assert r['requires_review'] and r['field_sources']['model']=='FreeVINDecoder'


def test_snapshot_bounded_and_workspace_isolation(logged,client):
    from conftest import signup
    a=logged.post('/api/v1/vehicles',json=values(VINS[0])).json()
    signup(client,'other-vin@example.test')
    assert client.get('/api/v1/vehicles/'+a['id']).status_code==404
    assert client.post('/api/v1/vehicles',json=values(VINS[0])).status_code==201
    data=values(VINS[1]);data['vin_details']['decoded']['secret_payload']='not accepted'
    assert logged.post('/api/v1/vehicles',json=data).status_code==422


def test_primary_fixture_decode_reports_fields_and_never_calls_paid_provider(logged,monkeypatch):
    import json
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps({'Results':[{'Make':'Volvo','Model':'Fixture','ModelYear':'2020','EngineModel':'FIXTURE','TransmissionStyle':'Automatic','DriveType':'AWD','Doors':'5','ErrorCode':'0'}]}).encode()
    monkeypatch.setattr(vin_lookup,'urlopen',lambda *a,**k:Reply())
    monkeypatch.setattr('app.services.vin_freevindecoder.decode_page',lambda v:None)
    monkeypatch.setattr('app.services.vin_europe.europe_vin',lambda *a:(_ for _ in ()).throw(AssertionError('Paid provider must not run')))
    for vin in VINS:
        data=logged.get('/api/v1/vehicles/vin/decode?vin='+vin).json()
        assert data['vehicle']['doors']=='5' and data['field_sources']['doors']=='NHTSA vPIC'
        assert data['requires_review'] and data['source']=='NHTSA vPIC'


def test_concurrent_duplicate_vin_serialized(logged):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda _:logged.post('/api/v1/vehicles',json=values(VINS[0])).status_code,range(2)))
    assert sorted(codes)==[201,409]


def test_nullable_additive_migration_shape(monkeypatch):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import inspect
    from app.db import engine
    columns={c['name']:c for c in inspect(engine()).get_columns('vehicles')}
    assert columns['vin_details']['nullable'] is True
    path=Path(__file__).resolve().parents[1]/'alembic/versions/08b72c9d4e16_vehicle_vin_details.py'
    spec=importlib.util.spec_from_file_location('vin_migration',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    calls=[];monkeypatch.setattr(mod.op,'add_column',lambda table,column:calls.append((table,column.name,column.nullable)))
    mod.upgrade();assert calls==[('vehicles','vin_details',True)] and mod.down_revision=='f7a10b8c43d2'


def test_vin_intake_does_not_mutate_existing_donor_or_stock(logged,vehicle,part):
    before_vehicle=logged.get('/api/v1/vehicles/'+vehicle['id']).json()
    before_part=logged.get('/api/v1/parts/'+part['id']).json()
    assert logged.post('/api/v1/vehicles',json=values(VINS[0])).status_code==201
    assert logged.get('/api/v1/vehicles/'+vehicle['id']).json()==before_vehicle
    assert logged.get('/api/v1/parts/'+part['id']).json()==before_part
