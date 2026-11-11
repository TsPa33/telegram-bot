"""Offline source ambiguity and free, generic plans; no actual Peugeot facts asserted."""
import json
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Part,Vehicle,DismantlingItem
from app.services import vin_lookup,vin_freevindecoder,unified_catalogue


def test_ambiguous_provider_year_is_not_silently_saved_as_1987(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*a):return json.dumps({'Results':[dict(Make='PEUGEOT',Model='5008',ModelYear='1987',ErrorCode='10',ErrorText='Model year may not be valid')]}).encode()
    vin_lookup.clear_cache();monkeypatch.setattr(vin_lookup,'urlopen',lambda *a,**k:Response());monkeypatch.setattr(vin_freevindecoder,'decode_page',lambda vin:None)
    r=vin_lookup.lookup('VF3AAAAA0H0000001')
    assert 'year' not in r['vehicle'] and 'year' in r['consistency_issues']
    assert r['diagnostics']['year_observation']['reported_year']=='1987'
    vin_lookup.clear_cache()


@pytest.mark.parametrize('maker,model,year,vin',[('PEUGEOT','5008',1987,'VF3AAAAA0H0000001'),('Renault','ZOE',2020,''),('Volkswagen','Golf',2019,'WVWAAAAA0K0000001')])
def test_empty_donor_always_has_free_generic_plan(logged,monkeypatch,maker,model,year,vin):
    monkeypatch.setenv('PLAN_PARTS_ENABLED','false');monkeypatch.delenv('PLAN_PARTS_API_KEY',raising=False)
    monkeypatch.setattr(unified_catalogue.CatalogueAdapter,'plan',lambda *a,**k:pytest.fail('No exact source lookup without selection'))
    data=dict(manufacturer=maker,model=model,year=year)
    if vin:data['vin']=vin
    created=logged.post('/api/v1/vehicles',json=data);assert created.status_code==201,created.text
    v=created.json();path=f"/api/v1/vehicles/{v['id']}/dismantling-v3"
    p=logged.post(path+'/preview',json={'facts':[],'universal':True});assert p.status_code==200,p.text
    assert p.json()['catalogue_status']['generator']['types']==216
    body=dict(facts=[],universal=True,token=p.json()['token'],request_key=str(uuid4()),confirm=True)
    assert logged.post(path+'/save',json=body).status_code==200
    assert logged.post(path+'/save',json=body).status_code==200
    with Session(engine()) as db:
        assert db.get(Vehicle,v['id']).year==year # Never rewrite the existing owner's facts.
        assert db.scalar(select(func.count()).select_from(DismantlingItem))==227
        assert db.scalar(select(func.count()).select_from(Part))==0


def test_vin_uncertainty_roundtrip(logged):
    details={'source':'offline_fixture','characteristics':{'year':'2021'},'decoded':{'year':2022},'consistency_issues':{'year':'Перевірте рік'},'diagnostics':{'year_observation':{'reported_year':'1987','reason':'provider_model_year_uncertain','codes':['10']}}}
    r=logged.post('/api/v1/vehicles',json={'manufacturer':'PEUGEOT','model':'5008','year':2021,'vin_details':details})
    assert r.status_code==201,r.text
    saved=logged.get('/api/v1/vehicles/'+r.json()['id']).json()['vin_details']
    assert saved['diagnostics']['year_observation']['reported_year']=='1987'
    assert saved['characteristics']['year']=='2021' and saved['decoded']['year']==2022
    invalid={**details,'diagnostics':{'unexpected':'Not allowed'}}
    assert logged.post('/api/v1/vehicles',json={'manufacturer':'Test','model':'Invalid','year':2021,'vin_details':invalid}).status_code==422
