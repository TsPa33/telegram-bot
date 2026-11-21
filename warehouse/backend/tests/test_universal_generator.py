"""Synthetic configurations and catalogue contracts, never live Volvo fitment evidence."""
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Vehicle,Part,DismantlingItem,Operation,AssemblyMembership
from app.services import unified_catalogue as catalogue


def preview(c,v):
    r=c.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/preview",json={'facts':[],'universal':True})
    assert r.status_code==200,r.text
    return r.json()

def save(c,v,p,key=None):
    return c.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/save",json=dict(facts=[],universal=True,token=p['token'],request_key=key or str(uuid4()),confirm=True))

@pytest.mark.parametrize('make,model,year,details',[('Volvo','XC60',2022,{}),('Volvo','XC90',2016,{}),('Volkswagen','Golf',2019,{}),('Renault','ZOE',2020,{'electrification':'Електромобіль (BEV)','body_class':'Хетчбек'})])
def test_one_generator_all_makes_unknowns_repeat_and_no_stock(logged,monkeypatch,make,model,year,details):
    monkeypatch.setattr(catalogue.CatalogueAdapter,'plan',lambda *a,**k:pytest.fail('No remote calls without explicit modification'))
    r=logged.post('/api/v1/vehicles',json={'manufacturer':make,'model':model,'year':year,'vin_details':{'characteristics':details}});assert r.status_code==201
    v=r.json();p=preview(logged,v);g=p['catalogue_status']['generator']
    from collections import Counter
    print('GENERATOR_CASE',make,model,year,{'types':g['types'],'positions':g['positions'],'categories':g['categories'],'states':dict(Counter(i['item']['applicability_status'] for i in p['proposals']))})
    assert g['types']>100 and g['positions']>=g['types'] and not g['complete']
    assert any(i['item']['applicability_status']=='unknown' for i in p['proposals'])
    assert not any(i['item']['source_confirmed'] for i in p['proposals'])
    key=str(uuid4());s=save(logged,v,p,key);assert s.status_code==200,s.text
    assert save(logged,v,p,key).json()==s.json()
    with Session(engine()) as db:
        count=db.scalar(select(func.count()).select_from(DismantlingItem));assert count>100
        assert db.scalar(select(func.count()).select_from(Part))==0
    again=preview(logged,v);s=save(logged,v,again);assert s.status_code==200,s.text
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(DismantlingItem))==count
    assert logged.get(f"/api/v1/vehicles/{v['id']}/dismantling-v3").json()['generator']['types']==g['types']


def test_regeneration_preserves_two_manual_decisions_stock_reserves_and_membership(logged,vehicle):
    p=preview(logged,vehicle);assert save(logged,vehicle,p).status_code==200
    with Session(engine()) as db:
        nodes=list(db.scalars(select(DismantlingItem).order_by(DismantlingItem.id).limit(2)))
        for n in nodes:n.plan_v3={**n.plan_v3,'inspection':'present','inspection_source':'user_decision','inspection_note':'Private synthetic note'}
        part=Part(account_id=nodes[0].account_id,vehicle_id=vehicle['id'],name='Synthetic physical part',quantity=1,reserved_quantity=1,selling_price=500,currency='USD')
        db.add(part);db.flush();nodes[0].part_id=part.id
        op=Operation(account_id=part.account_id,actor_id=part.account_id,vehicle_id=vehicle['id'],entity_id=nodes[0].id,entity_type='assembly_memberships',type='assembly_attach',reason='Synthetic fixture',before={},after={})
        db.add(op);db.flush();edge=AssemblyMembership(account_id=part.account_id,vehicle_id=vehicle['id'],parent_item_id=nodes[0].id,child_item_id=nodes[1].id,attached_operation_id=op.id)
        db.add(edge);db.flush();ids=[n.id for n in nodes];partid=part.id;edgeid=edge.id;opid=op.id;db.commit()
    p=preview(logged,vehicle);assert save(logged,vehicle,p).status_code==200
    with Session(engine()) as db:
        for id in ids:
            n=db.get(DismantlingItem,id);assert n.plan_v3['inspection']=='present' and n.plan_v3['inspection_note']=='Private synthetic note'
        p=db.get(Part,partid);assert (p.quantity,p.reserved_quantity,p.currency,float(p.selling_price))==(1,1,'USD',500.0)
        assert db.get(AssemblyMembership,edgeid).active and db.get(Operation,opid).type=='assembly_attach'


def test_exact_generic_modification_partial_source_is_distinct_from_physical(logged,monkeypatch):
    from test_unified_catalogue import envelope
    payload=envelope(car=456,coverage='partial')['payload'];payload.update(schema='carpot.vehicle.plan.v1',manufacturer_id=987,model_id=654)
    v=logged.post('/api/v1/vehicles',json={'manufacturer':'Other brand','model':'Synthetic model','year':2020}).json()
    with Session(engine()) as db:
        row=db.get(Vehicle,v['id']);row.dismantling_v3={'global_selection':dict(car_id=456,model_id=654,manufacturer_id=987,source_snapshot_sha=payload['source_snapshot_sha'],vehicle_basis=catalogue.vehicle_basis(row))};db.commit()
    monkeypatch.setattr(catalogue.CatalogueAdapter,'plan',lambda *a,**k:{'payload':payload})
    with Session(engine()) as db:
        row=db.get(Vehicle,v['id']);legacy=DismantlingItem(account_id=row.account_id,vehicle_id=row.id,source='carpot.catalogue.v1',catalog_key='car:456:product:106',category_key='legacy',category_name='Освітлення',subcategory_key='legacy',subcategory_name='Передні фари',name='Manual historical name',quantity=1,plan_v3={'inspection':'present','inspection_source':'user_decision'});db.add(legacy);db.flush();legacy_id=legacy.id;db.commit()
    conflicts=[dict(field='powertrain',value=x,kind='manual',reference='Synthetic conflict fixture') for x in ('petrol','BEV')]
    conflict=logged.post(f"/api/v1/vehicles/{v['id']}/dismantling-v3/preview",json={'facts':conflicts,'universal':True}).json()
    assert conflict['configuration']['conflicts'] and not conflict['proposals'][0]['item']['source_confirmed']
    p=preview(logged,v);assert p['catalogue_status']['generator']['exact_source_positions']==1
    assert p['proposals'][0]['item']['source_confirmed']
    assert save(logged,v,p).status_code==200
    with Session(engine()) as db:
        n=db.scalar(select(DismantlingItem));assert n.id==legacy_id and n.name=='Manual historical name' and n.plan_v3['inspection']=='present' and not n.part_id
    p=preview(logged,v);assert p['counts']['new']==0 and save(logged,v,p).status_code==200


def test_verified_constraints_reject_but_reported_unknown_never_excludes():
    from app.services.universal_generator import explicit_rule
    rule=dict(when={'powertrain':['BEV']},effect='incompatible',evidence='Synthetic reviewed rule for a combustion-only type')
    base=dict(values={'powertrain':'BEV'},provenance={'powertrain':{'confidence':'reported'}},conflicts=[])
    assert explicit_rule([rule],base)['status']=='unknown'
    base['provenance']['powertrain']['confidence']='verified'
    assert explicit_rule([rule],base)['status']=='incompatible'
    base['conflicts']=['contradictory facts'];assert explicit_rule([rule],base)['status']=='unknown'


def test_changed_vin_attributes_invalidates_preview_and_scope(logged,vehicle,client):
    p=preview(logged,vehicle);assert save(logged,vehicle,p).status_code==200
    p=preview(logged,vehicle)
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.vin_details={'characteristics':{'electrification':'Електромобіль (BEV)'}};db.commit()
    assert save(logged,vehicle,p).status_code==409
    assert logged.get(f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3").json()['generator_stale']
    from conftest import signup
    signup(client,'other-generator@example.test')
    assert client.post(f"/api/v1/vehicles/{vehicle['id']}/dismantling-v3/preview",json={'facts':[],'universal':True}).status_code==404


def test_verified_bev_and_published_prd_extension_without_new_generation_logic(logged):
    from app.models.canonical import CanonicalType,CanonicalPlacement
    from app.services.canonical_rules import type_record,placement
    v=logged.post('/api/v1/vehicles',json={'manufacturer':'Other EV maker','model':'Synthetic EV','year':2020,'fuel_type':'Електро'}).json()
    configuration=f"/api/v1/vehicles/{v['id']}/configuration"
    facts=[dict(field='powertrain',value='BEV',kind='document',reference='Synthetic verified engineering evidence, not real vehicle fitment',confidence='verified')]
    r=logged.post(configuration+'/preview',json={'facts':facts});assert r.status_code==200,r.text
    p=r.json();r=logged.post(configuration+'/confirm',json={'preview_id':p['id'],'token':p['token'],'confirm':True});assert r.status_code==200,r.text
    t=type_record('Synthetic combustion-only PRD fixture','Двигун та його системи','Система запалювання')
    t['provenance']={'universal_publication':'offline_owner_review_fixture','universal_sources':[{'source_key':'td1q2018:prd:999998'}],'fitment_rules':[{'when':{'powertrain':['BEV']},'effect':'incompatible','evidence':'Synthetic combustion-only function restriction'}]}
    pos=placement(dict(type_id=t['id'],installation={'side':'unknown','position':'unknown','mount':[]}))
    with Session(engine()) as db:db.add(CanonicalType(**t));db.flush();db.add(CanonicalPlacement(**pos));db.commit()
    p=preview(logged,v);assert p['catalogue_status']['generator']['published_reference_positions']==1
    item=next(i['item'] for i in p['proposals'] if i['item']['canonical_part_type_id']==t['id'])
    assert item['applicability_status']=='incompatible'
    assert any(i['item']['applicability_status']=='unknown' for i in p['proposals'])
    assert all(i['item']['variants']==[] for i in p['proposals'])  # No fabricated articles/OEM.

    with Session(engine()) as db:
        row=db.get(Vehicle,v['id']);row.vin_details={'characteristics':{'electrification':'Гібрид (HEV)'}};db.commit()
    conflict=preview(logged,v)
    assert conflict['configuration']['conflicts']
    changed=next(i['item'] for i in conflict['proposals'] if i['item']['canonical_part_type_id']==t['id'])
    assert changed['applicability_status']=='unknown'
