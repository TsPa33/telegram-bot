"""Offline vPIC/HTML fixtures only; never factual specifications for the supplied VINs."""
import json
import pytest
from app.services import vin_lookup as service,vin_freevindecoder as free
from app.services.vin_normalize import ukrainian

VIN='YV4L12RK6N1970668'
@pytest.fixture(autouse=True)
def reset(monkeypatch):
    service.clear_cache();free._cache.clear();free._status.clear()
    monkeypatch.setattr(free,'_policy',None);monkeypatch.setattr(free,'_policy_expires',0);monkeypatch.setattr(free,'_last_request',0)
    yield
    service.clear_cache()

class Reply:
    def __init__(self,body,status=200,headers=None):self.body=body;self.status=status;self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,*a):return self.body


def primary(monkeypatch,row):
    monkeypatch.setattr(service,'urlopen',lambda *a,**k:Reply(json.dumps({'Results':[row]}).encode()))


def test_enrichment_despite_core_fields_and_structured_extra(monkeypatch):
    primary(monkeypatch,dict(Make='Volvo',Model='OFFLINE',ModelYear='2020',EngineModel='B-CODE-DESCRIPTION',TransmissionStyle='Automatic',EngineHP='250',FuelTypeSecondary='Electric',ElectrificationLevel='Mild HEV (Hybrid Electric Vehicle)',TransmissionSpeeds='8',BrakeSystemType='Hydraulic',Turbo='Yes',PlantCity='TORS LANDA',ErrorCode='0'))
    calls=[]
    def secondary(vin):calls.append(vin);return {'engine_code':'EXPLICIT-TEST-CODE','doors':'5','model':'CONFLICTING FIXTURE'}
    monkeypatch.setattr(free,'decode_page',secondary)
    result=service.lookup(VIN)
    assert calls==[VIN]  # Old implementation skipped this when its four core fields were present.
    assert result['vehicle']['engine_code']=='EXPLICIT-TEST-CODE'
    assert result['vehicle']['engine']=='B-CODE-DESCRIPTION'
    assert result['vehicle']['model']=='OFFLINE' and 'model' in result['conflicts']
    assert result['field_sources']['doors']=='FreeVINDecoder'
    assert result['vehicle']['fuel_secondary']=='Електро'
    assert result['vehicle']['plant_city']=='TORS LANDA'
    assert result['additional']['turbo']['value']=='Так'
    assert result['counts']['conflicting']==1
    assert result['vehicle']['transmission_speeds']=='8'


def test_model_description_never_becomes_code_and_cache_isolated_copies(monkeypatch):
    calls=[]
    def source(*a,**k):calls.append(1);return Reply(json.dumps({'Results':[{'Make':'Other manufacturer','Model':'Fixture','ModelYear':'2020','EngineModel':'MODEL-ONLY'}]}).encode())
    monkeypatch.setattr(service,'urlopen',source);monkeypatch.setattr(free,'decode_page',lambda v:None)
    a=service.lookup(VIN);a['vehicle']['model']='CLIENT MUTATION'
    b=service.lookup(VIN)
    assert len(calls)==1 and b['cached'] and b['vehicle']['model']=='Fixture'
    assert 'engine_code' not in b['vehicle'] and 'engine_code' in b['missing_fields']
    monkeypatch.setattr(service,'monotonic',lambda:10**30)
    service.lookup(VIN);assert len(calls)==2


def test_normalization_preserves_factory_identifiers():
    assert ukrainian('drive_type','AWD/All-Wheel Drive')=='Повний привід (AWD)'
    assert ukrainian('body_class','Sport Utility Vehicle (SUV)')=='Позашляховик (SUV)'
    assert ukrainian('transmission','Automatic')=='Автоматична КПП'
    for key,val in [('plant_city','TORS LANDA'),('plant_city','TORSLANDA'),('engine_code','B4204T27'),('transmission_code','TG-81SC')]:assert ukrainian(key,val)==val


def test_explicit_html_labels_and_robots_denial(monkeypatch):
    html='<table><tr><td>Make</td><td>Fixture</td></tr><tr><td>Model</td><td>Fixture</td></tr><tr><td>Engine Type</td><td>MODEL-ONLY</td></tr><tr><td>Fuel Type</td><td>Electric</td></tr></table>'
    data=free.extract_page(html,VIN);assert data['fuel_type']=='Electric' and 'engine_code' not in data
    calls=[]
    def policy(req,**kw):calls.append(req.full_url);return Reply(b'User-agent: *\nDisallow: /\n')
    monkeypatch.setattr(free,'urlopen',policy)
    assert free.decode_page(VIN) is None and free.source_status(VIN)=='robots_denied'
    assert len(calls)==1 and calls[0].endswith('/robots.txt')


def test_extra_attributes_persist_without_migration(logged):
    payload=dict(manufacturer='Other manufacturer',model='OFFLINE',year=2020,vin=VIN,drive_type='Повний привід (AWD)',
      vin_details=dict(characteristics={'fuel_secondary':'Електро','electrification':'М’який гібрид (MHEV)','transmission_speeds':'8'},
       additional={'turbo':{'label':'Турбонаддув','value':'Так','source':'offline_fixture'}},
       decoded_additional={'turbo':{'label':'Турбонаддув','value':'Так','source':'offline_fixture'}}))
    r=logged.post('/api/v1/vehicles',json=payload);assert r.status_code==201,r.text
    saved=logged.get('/api/v1/vehicles/'+r.json()['id']).json()
    assert saved['drive_type']=='AWD'
    for key,value in payload['vin_details']['additional']['turbo'].items():assert saved['vin_details']['additional']['turbo'][key]==value
    assert saved['vin_details']['characteristics']['fuel_secondary']=='Електро'
