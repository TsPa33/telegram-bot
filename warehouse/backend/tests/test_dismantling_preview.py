"""Stage 2A: read-only configuration preview, conservative rules and evidence."""
import json,os
from datetime import datetime,timezone
from pathlib import Path
import pytest
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Vehicle
from app.services.vin_adapter import OfflineVinAdapter,DecodeResult
from test_catalogue_v2 import platform,row,plan,upload,confirm
from test_canonical_v3 import market,build,fingerprints,item,PREFIX

def setup_vehicle(vehicle):
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.manufacturer='Volvo';v.model='XC40';v.year=2020;v.engine='';v.fuel_type='';v.transmission='';v.generation='';db.commit()
def run(c,v,facts=None):return c.post(f"/api/v1/vehicles/{v['id']}/dismantling-preview",json={'facts':facts or []})
def fact(field,value,confidence='reported'):return dict(field=field,value=value,kind='manual',reference='Local engineering review',confidence=confidence)
def save_config(c,v,values):
    path=f"/api/v1/vehicles/{v['id']}/configuration"
    p=c.post(path+'/preview',json={'facts':[fact(k,value,'verified') for k,value in values.items()]}).json()
    r=c.post(path+'/confirm',json={'preview_id':p['id'],'token':p['token'],'confirm':True});assert r.status_code==200,r.text

@pytest.mark.parametrize('powertrain',['petrol','diesel','HEV','PHEV','BEV'])
@pytest.mark.parametrize('drive',['FWD','AWD'])
def test_trial_configuration_never_confirms_or_writes(platform,vehicle,powertrain,drive):
    setup_vehicle(vehicle);market(platform,[item(str(i)) for i in range(5)]);build(platform)
    with Session(engine()) as db:before=fingerprints(db)
    a=run(platform,vehicle,[fact('powertrain',powertrain),fact('drive',drive)]);assert a.status_code==200,a.text
    b=run(platform,vehicle,[fact('powertrain',powertrain),fact('drive',drive)]).json()
    assert a.json()==b and b['read_only'] and not b['persisted']
    assert b['status_counts']['confirmed']==0
    generators=[i for i in b['items'] if i['name']=='Генератор']
    assert len(generators)==1 and generators[0]['relevant_offer_count']==5 and len(generators[0]['variants'])==5
    with Session(engine()) as db:assert fingerprints(db)==before

def test_unknown_configuration_base_without_publication_and_conflicts(platform,vehicle):
    setup_vehicle(vehicle)
    a=run(platform,vehicle).json();assert a['total']==33 and not a['published'] and a['status_counts']['confirmed']==0
    b=run(platform,vehicle,[fact('powertrain','BEV'),fact('fuel_type','diesel')]).json()
    assert b['configuration']['conflicts'] and b['total']==33 and b['status_counts']['unknown']==33

@pytest.mark.parametrize('vin',['','ABC','I2345678901234567','12345678901234567?'])
def test_vin_invalid(vin):
    with pytest.raises(ValueError):OfflineVinAdapter().decode(vin)

def test_partial_vin_contract_no_invented_options():
    data=OfflineVinAdapter().decode('yv1xz72acm1234567');assert data.vin=='YV1XZ72ACM1234567' and data.facts==[] and not data.complete
    result=DecodeResult(vin=data.vin,adapter='test-fixture',version='1',facts=[dict(field='year',value=2020,kind='vin_decode',reference='Partial fixture only',confidence='reported')])
    assert [f.field for f in result.facts]==['year']

def test_explicit_fitment_and_cross_model_rule_source(platform,vehicle):
    setup_vehicle(vehicle)
    market(platform,[item('other',model='XC90')]);build(platform)
    r=platform.get('/api/v1/catalogue/canonical/candidates',params={'manufacturer':'Volvo','model':'XC90'}).json()
    variant=next(i for i in r['items'] if i['name']=='Генератор')['variants'][0]
    evidence=platform.post(PREFIX+'/fitments',json={'variant_id':variant['id'],'manufacturer':'Volvo','model':'XC40','year_from':2020,'year_to':2020,'status':'confirmed','evidence':'Reviewed exact vehicle fitment document'})
    assert evidence.status_code==201,evidence.text
    save_config(platform,vehicle,{'manufacturer':'Volvo','model':'XC40','year':2020})
    a=run(platform,vehicle).json();g=next(i for i in a['items'] if i['name']=='Генератор')
    assert g['applicability_status']=='confirmed' and g['compatible_evidence']==[evidence.json()['id']]
    assert g['relevant_offer_count']==1
    trial=run(platform,vehicle,[fact('year',2021)]).json()
    assert trial['status_counts']['confirmed']==0

def test_verified_bev_constraint_is_visible_not_excluded(platform,vehicle):
    setup_vehicle(vehicle);market(platform,[item()]);build(platform)
    save_config(platform,vehicle,{'manufacturer':'Volvo','model':'XC40','year':2020,'powertrain':'BEV'})
    a=run(platform,vehicle).json();g=next(i for i in a['items'] if i['name']=='Генератор')
    assert g['applicability_status']=='incompatible' and a['total']>=33

def test_positions_oems_and_workspace_csrf(platform,vehicle):
    from fastapi.testclient import TestClient
    from app.main import app
    from conftest import signup
    setup_vehicle(vehicle)
    market(platform,[row(str(i),part_name=f"Фара передня {'ліва' if i<2 else 'права'} Volvo XC40",category='Електрика',subcategory='Фари',side='',position='',oem='A' if i%2 else 'B') for i in range(4)]);build(platform)
    a=run(platform,vehicle).json();lamps=[i for i in a['items'] if i['name']=='Фара']
    assert {i['installation_position']['side'] for i in lamps}=={'left','right'}
    assert len({i['canonical_part_type_id'] for i in lamps})==1
    with TestClient(app) as other:
        signup(other,'preview-other@example.test');assert run(other,vehicle).status_code==404
    token=platform.headers.pop('X-CSRF-Token');assert run(platform,vehicle).status_code==403;platform.headers['X-CSRF-Token']=token

def test_real_A_xc90_read_only_example(platform,vehicle,tmp_path):
    from app.services.aleto_import import BUNDLED_PACKAGE
    j=plan(platform,upload(platform,raw=BUNDLED_PACKAGE.read_bytes(),filename=BUNDLED_PACKAGE.name))
    if j['report']['issues']:j=plan(platform,j,{i['key']:{'action':'skip'} for i in j['report']['issues']})
    confirm(platform,j);build(platform);setup_vehicle(vehicle)
    with Session(engine()) as db:db.get(Vehicle,vehicle['id']).model='XC90';db.commit();before=fingerprints(db)
    result=run(platform,vehicle);assert result.status_code==200,result.text
    data=result.json();assert data['total']>=33 and data['status_counts']['confirmed']==0
    with Session(engine()) as db:assert before==fingerprints(db)
    out=Path(os.environ.get('WAREHOUSE_DISMANTLING_REPORT',str(tmp_path/'xc90-preview.json')))
    out.write_text(json.dumps(dict(dataset='real Volvo A',real_B_tested=False,vehicle='Volvo XC90 2020; unknown engine/equipment',total=data['total'],unique_type_count=data['unique_type_count'],type_status_counts=data['type_status_counts'],status_counts=data['status_counts'],unmapped_paths=data['unmapped_paths'],items=[{k:i[k] for k in ('id','canonical_part_type_id','name','installation_position','applicability_status','relevant_offer_count','price_label','reference_prices')} for i in data['items']]),ensure_ascii=False,indent=2)+'\n')

def test_comparable_prices_do_not_mix_oem_condition_dates_or_duplicates(platform,vehicle,monkeypatch):
    monkeypatch.setattr('app.services.dismantling_preview.utcnow',lambda:datetime(2026,10,28,tzinfo=timezone.utc))
    setup_vehicle(vehicle)
    rows=[]
    for i,price in enumerate(('10','20','30')):
        r=row(str(i),part_name='Генератор Volvo XC40',category='Електрика',subcategory='Генератори',side='',position='',oem='COMPARABLE-OEM',condition='used-tested',price_uah=price,price_usd='')
        rows.extend([r,dict(r,category='Двигун')])
    for article,oem,condition,date in [('other-oem','OTHER','used-tested','2026-10-27T12:00:00Z'),('condition','COMPARABLE-OEM','damaged','2026-10-27T12:00:00Z'),('stale','COMPARABLE-OEM','used-tested','2025-01-01T00:00:00Z'),('future','COMPARABLE-OEM','used-tested','2030-01-01T00:00:00Z')]:
        rows.append(row(article,part_name='Генератор Volvo XC40',category='Електрика',subcategory='Генератори',side='',position='',oem=oem,condition=condition,price_uah='999',price_usd='',observed_at=date))
    rows.append(row('cosmetic',part_name='Генератор Volvo XC40 подряпини',category='Електрика',subcategory='Генератори',side='',position='',oem='COMPARABLE-OEM',condition='used-tested',price_uah='999',price_usd=''))
    market(platform,rows);build(platform)
    data=run(platform,vehicle).json();g=next(i for i in data['items'] if i['name']=='Генератор')
    assert len(g['reference_prices'])==1
    p=g['reference_prices'][0];assert p['offer_count']==3 and p['minimum']=='10.00' and p['median']=='20.00' and p['maximum']=='30.00' and p['currency']=='UAH'
    assert g['selling_price'] is None


def test_factory_option_rule_missing_is_unknown_not_hidden(platform,vehicle):
    setup_vehicle(vehicle)
    market(platform,[row('roof',model='XC90',part_name='Привід панорамного даху Volvo XC90',category='Кузов',subcategory='Дах',side='',position='')])
    t=platform.post(PREFIX+'/types',json={'name':'Привід панорамного даху','category':'Кузов','subcategory':'Дах','evidence':'Inspected optional roof motor function'}).json()['id']
    assert platform.post(PREFIX+'/aliases',json={'type_id':t,'phrase':'привід панорамного даху','category':'Кузов','subcategory':'Дах','evidence':'Reviewed exact roof function'}).status_code==201
    build(platform)
    candidates=platform.get('/api/v1/catalogue/canonical/candidates',params={'manufacturer':'Volvo','model':'XC90'}).json()
    v=next(i for i in candidates['items'] if i['name']=='Привід панорамного даху')['variants'][0]
    assert platform.post(PREFIX+'/fitments',json={'variant_id':v['id'],'manufacturer':'Volvo','model':'XC40','year_from':2020,'year_to':2020,'options':['panoramic-roof'],'status':'confirmed','evidence':'Reviewed roof build-sheet and exact part application'}).status_code==201
    unknown=run(platform,vehicle).json();g=next(i for i in unknown['items'] if i['name']=='Привід панорамного даху')
    assert g['applicability_status']=='unknown'
    save_config(platform,vehicle,{'manufacturer':'Volvo','model':'XC40','year':2020,'options':['panoramic-roof']})
    confirmed=run(platform,vehicle).json();g=next(i for i in confirmed['items'] if i['name']=='Привід панорамного даху')
    assert g['applicability_status']=='confirmed'

def test_read_only_employee_without_edit_permission(platform,vehicle,monkeypatch):
    from test_team import employee,activate
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    setup_vehicle(vehicle)
    _,data=employee(platform,['vehicles.view','catalog.view'])
    c=activate(data)
    try:
        with Session(engine()) as db:before=fingerprints(db)
        result=run(c,vehicle);assert result.status_code==200,result.text
        assert result.json()['configuration']['values']['model']=='XC40'
        assert c.post(f"/api/v1/vehicles/{vehicle['id']}/configuration/preview",json={'facts':[]}).status_code==403
        with Session(engine()) as db:assert fingerprints(db)==before
    finally:c.close()


def test_existing_stock_sales_plan_and_audit_unchanged(platform,vehicle,part):
    setup_vehicle(vehicle)
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'receipt','quantity':3,'reason':'Existing stock before preview'}).status_code==200
    assert platform.post(f"/api/v1/parts/{part['id']}/operations",json={'type':'sale','quantity':1,'sale_price':'77.77','sale_currency':'USD','request_key':'c5e899a0-2f27-44d1-94fe-41d8fd30b402'}).status_code==200
    assert platform.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling/start").status_code==200
    from sqlalchemy import select
    from app.models import DismantlingItem
    with Session(engine()) as db:
        db.scalar(select(DismantlingItem).limit(1)).included=False;db.commit();before=fingerprints(db)
    assert run(platform,vehicle,[fact('powertrain','BEV')]).status_code==200
    assert run(platform,vehicle).status_code==200
    with Session(engine()) as db:assert fingerprints(db)==before


def test_conflicting_fitment_evidence_never_becomes_possible_or_confirmed():
    from app.services.dismantling_preview import status_for
    result=status_for({'compatibility':{'status':'unknown','evidence_ids':['positive','negative']}},{'groups':['A'],'missing_or_unverified':[],'conflicting_fields':[]},{'reviewed':True,'conflicts':[],'values':{},'provenance':{}})
    assert result[0]=='unknown'
