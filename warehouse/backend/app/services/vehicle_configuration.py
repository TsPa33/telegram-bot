"""VIN-ready facts contract. No decoder/network calls and no Vehicle/Part writes."""
from collections import defaultdict
import re
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.vehicle_configuration import VehicleConfiguration as Configuration
from app.services.catalogue_format import digest
from app.services.canonical_rules import sid
from app.schemas.vehicle_configuration import FIELDS

BASIS=('manufacturer','model','generation','year','engine','fuel_type','transmission','vin')
def basis(vehicle):return digest({k:getattr(vehicle,k) for k in BASIS})

def baseline(vehicle):
    values={k:getattr(vehicle,k) or None for k in ('manufacturer','model','generation','year','fuel_type','transmission','vin')}
    values['engine_label']=vehicle.engine or None
    values['engine_code']=vehicle.engine if re.fullmatch(r'(?:[BD]\d{4}[A-Z]\d{0,3}|[BNSM]\d{2}[A-Z]\d{2}[A-Z0-9]{0,3})',vehicle.engine or '') else None
    values.update(powertrain=None,drive=None,body_type=None,options=None,options_complete=False)
    return values


def resolve(vehicle,facts,selected):
    values=baseline(vehicle);provenance={k:{'kind':'vehicle_record','confidence':'reported','reference':'Existing structured vehicle field'} for k,v in values.items() if v is not None and k!='options_complete'}
    grouped=defaultdict(list);conflicts=[]
    for i,fact in enumerate(facts):grouped[fact['field']].append((i,fact))
    for field,index in selected.items():
        if field not in FIELDS or type(index) is not int or not 0<=index<len(facts) or facts[index]['field']!=field:raise HTTPException(422,'Обране джерело не відповідає полю')
    for field,entries in grouped.items():
        different={digest(f['value']) for _,f in entries}
        if len(different)>1 and field not in selected:
            conflicts.append({'field':field,'reason':'Conflicting facts need an explicit source selection'});values[field]=None;continue
        chosen=next(((i,f) for i,f in entries if i==selected[field]),None) if field in selected else sorted(entries,key=lambda x:(x[1]['confidence']!='verified',x[0]))[0]
        if chosen is None:raise HTTPException(422,'Неправильний вибір джерела')
        i,fact=chosen;values[field]=fact['value'];provenance[field]={k:fact[k] for k in ('kind','reference','confidence')}
        provenance[field].update(selected_fact=i,alternatives=[n for n,_ in entries if n!=i])
    if vehicle.vin and values.get('vin') and vehicle.vin.upper()!=str(values['vin']).upper():conflicts.append({'field':'vin','reason':'VIN does not match the vehicle identity'})
    if values.get('powertrain')=='BEV' and (values.get('fuel_type') in ('petrol','diesel') or values.get('engine_code')):
        conflicts.append({'field':'powertrain','reason':'BEV contradicts an internal-combustion engine/fuel claim'})
    if values.get('powertrain') in ('petrol','diesel') and values.get('fuel_type') not in (None,values['powertrain']):conflicts.append({'field':'fuel_type','reason':'Fuel contradicts the explicitly stated powertrain'})
    if values.get('options_complete') and values.get('options') is None:conflicts.append({'field':'options','reason':'Complete options document must specify the actual codes, including an explicitly empty list'})
    missing=[field for field in sorted(FIELDS-{'vin','options_complete'}) if values.get(field) in (None,'') or provenance.get(field,{}).get('confidence')!='verified']
    return {'contract_version':1,'values':values,'provenance':provenance,'conflicts':conflicts,'missing_or_unverified':missing,'factory_configuration_inferred':False,'complete':not missing and not conflicts}


def preview(db,vehicle,who,facts,selected):
    report=resolve(vehicle,facts,selected);sha=basis(vehicle)
    token=digest([who.workspace_account_id,vehicle.id,who.actor_id,sha,facts,selected,report])
    rid=sid('vehicle-configuration-preview',token)
    db.execute(insert(Configuration).values(id=rid,account_id=who.workspace_account_id,vehicle_id=vehicle.id,actor_id=who.actor_id,status='preview',basis_sha=sha,token=token,facts=facts,report=report).on_conflict_do_nothing(index_elements=['id']))
    db.commit();return db.get(Configuration,rid)


def confirm(db,vehicle,who,preview_id,token):
    row=db.get(Configuration,preview_id)
    if not row or row.account_id!=who.workspace_account_id or row.vehicle_id!=vehicle.id or row.status!='preview':raise HTTPException(404,'Конфігурацію не знайдено')
    if row.token!=token or row.basis_sha!=basis(vehicle) or row.report['conflicts']:raise HTTPException(409,'Конфігурація застаріла або має конфлікти; потрібна нова перевірка')
    rid=sid('vehicle-configuration-confirmed',row.id,who.actor_id)
    db.execute(insert(Configuration).values(id=rid,account_id=who.workspace_account_id,vehicle_id=vehicle.id,actor_id=who.actor_id,status='confirmed',preview_id=row.id,basis_sha=row.basis_sha,token=row.token,facts=row.facts,report=row.report).on_conflict_do_nothing(index_elements=['id']))
    db.commit();return db.get(Configuration,rid)


def latest(db,vehicle,workspace):
    row=db.scalar(select(Configuration).where(Configuration.account_id==workspace,Configuration.vehicle_id==vehicle.id,Configuration.status=='confirmed').order_by(Configuration.created_at.desc(),Configuration.id.desc()).limit(1))
    if not row:return None
    return {'id':row.id,'status':'confirmed' if row.basis_sha==basis(vehicle) else 'stale',**row.report}


def summary(row):
    # Avoid generic finance redaction of a JSON key called `value`; these are
    # engineering facts, permitted without financial permissions.
    return {'id':row.id,'status':row.status,'basis_sha':row.basis_sha,'token':row.token,'report':row.report,
        'source_facts':[{('observed_value' if k=='value' else k):v for k,v in f.items()} for f in row.facts],
        'created_at':row.created_at,'vehicle_id':row.vehicle_id}
