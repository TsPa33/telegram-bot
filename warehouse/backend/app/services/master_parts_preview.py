"""Pure construction preview, no DB/network writes. Candidate, not fitment."""
from collections import Counter, defaultdict
from pathlib import Path
import csv

VERSION = 'carpot.master.parts.preview.v0.2'
SIDES = ('L', 'R')
AXLE_FEATURES = {'differential':'driven','halfshaft':'halfshaft','cv_joint':'cv_joint','cv_boot':'cv_joint','subframe':'subframe','knuckle':'knuckle','shock':'shock','spring':'coil_spring','arm':'independent_suspension','stabilizer':'stabilizer','stabilizer_link':'stabilizer','stabilizer_bush':'stabilizer','ball_joint':'ball_joint','brake_disc':'disc_brakes','brake_pad':'disc_brakes','caliper':'disc_brakes','brake_hose':'hydraulic_brakes','abs_sensor':'abs','leaf_spring':'leaf_spring','air_spring':'air_suspension','brake_chamber':'spring_brake','brake_drum':'drum_brakes','brake_shoe':'drum_brakes','steering_rod':'rack_steering','steering_end':'steered','hub':'hub','hub_bearing':'hub','wheel':'wheel','tire':'wheel'}
COUNTS = {'piston':'cylinders','rod':'cylinders','spark_plug':'spark_plugs','ignition_coil':'ignition_coils','glow_plug':'glow_plugs','injector':'injectors','intake_valve':'intake_valves','exhaust_valve':'exhaust_valves','camshaft':'camshafts','head':'cylinder_heads','valve_cover':'valve_covers','engine_mount':'engine_mounts','radiator_fan':'radiator_fans','lambda':'lambda_sensors','trunk_strut':'trunk_struts','wiper':'wipers','parking_sensor':'parking_sensors','airbag':'airbags','seatbelt':'seatbelts','seat_frame':'seat_frames','seat_motor':'seat_motors','traction_motor':'traction_motors','traction_inverter':'traction_inverters','hv_battery':'hv_batteries','wheel_bolt':'wheel_bolts','nut':'nuts','head_bolts':'head_bolt_sets','rings':'piston_ring_sets','rear_fog':'rear_fog_lamps','propshaft':'propshafts','rear_seat':'rear_seat_assemblies','fuse_box':'fuse_boxes','cv_joint':'cv_joints','cv_boot':'cv_boots'}
SIDE_DOORS = {'door','door_glass','window_regulator','window_motor','door_lock','door_handle','inner_handle','door_trim','door_hinge','door_seal','door_check','door_speaker'}

def read_seed(path):
    out=[]
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'): continue
        key,name,cat,ids,cond,placement=line.split('|')
        out.append(dict(key=key,name_uk=name,category_path=cat.split('/'),prd_ids=[int(x) for x in ids.split(',') if x],condition=cond,placement_hint=placement))
    assert len({e['key'] for e in out})==len(out)
    assert len({i for e in out for i in e['prd_ids']})==sum(len(e['prd_ids']) for e in out)
    return out

def validate_profile(p):
    if p.get('kind') not in (None,'passenger','lcv','heavy_truck'): raise ValueError('unknown vehicle class')
    if p.get('body') not in (None,'sedan','hatch','suv','coupe','wagon','van','pickup','tractor','truck','convertible'): raise ValueError('unknown body')
    doors=p.get('side_doors')
    if doors is not None and (len(doors)!=len(set(doors)) or not set(doors)<= {'FL','FR','RL','RR','SL','SR'}): raise ValueError('invalid doors')
    if p.get('body')=='coupe' and doors is not None and any(x in doors for x in ('RL','RR','SL','SR')): raise ValueError('coupe door conflict')
    if p.get('rear_closure') not in (None,'none','lid','liftgate','split','tailgate'): raise ValueError('rear closure')
    if p.get('body')=='sedan' and p.get('rear_closure') in ('liftgate','split'): raise ValueError('sedan closure conflict')
    axles=p.get('axles')
    if axles is not None and (not 1<=len(axles)<=12 or any(a.get('wheel_count_per_side') not in (None,1,2) for a in axles)): raise ValueError('axles')
    for k,v in p.get('counts',{}).items():
        if type(v) is not int or not 0<=v<=128: raise ValueError('invalid count: '+k)
    if p.get('powertrain') not in (None,'ICE','HEV','PHEV','BEV'): raise ValueError('powertrain')
    if p.get('powertrain')=='BEV' and (p.get('fuel') in ('petrol','diesel') or p.get('flags',{}).get('ice') is True): raise ValueError('BEV conflict')
    if any(type(v) is not bool and v is not None for v in p.get('flags',{}).values()): raise ValueError('invalid flag')

def condition(p, key):
    k=p.get('kind'); power=p.get('powertrain'); fuel=p.get('fuel'); trans=p.get('transmission')
    derived={'all': True if k in ('passenger','lcv','heavy_truck') else None,'passenger':k in ('passenger','lcv') if k else None,'heavy_truck':k=='heavy_truck' if k else None,'ice':power!='BEV' if power else None,'conventional_ice':power=='ICE' if power else None,'electric_drive':power!='ICE' if power else None,'plug_in':power in ('BEV','PHEV') if power else None,'petrol':False if power=='BEV' else (fuel=='petrol' if fuel else None),'diesel':False if power=='BEV' else (fuel=='diesel' if fuel else None),'automatic':trans=='automatic' if trans else None,'manual':trans=='manual' if trans else None,'tractor':p.get('body')=='tractor' if p.get('body') else None,'trunk_lid':p.get('rear_closure')!='none' if p.get('rear_closure') else None,'rear_seat':p.get('counts',{}).get('rear_seat_assemblies',None)}
    if key=='rear_seat' and derived[key] is not None: return derived[key]>0
    d=derived.get(key); f=p.get('flags',{}).get(key)
    if d is not None and f is not None and d!=f: raise ValueError('profile conflict: '+key)
    return d if d is not None else f

def placements(entry,p):
    """Return (positions, unresolved). No fabricated positions for unknown topology."""
    key=entry['key']; hint=entry['placement_hint']; count=p.get('counts',{}); axles=p.get('axles')
    if key=='battery': applied=condition(p,'low_voltage_battery')
    elif key in AXLE_FEATURES: applied=condition(p,'all')
    elif key in SIDE_DOORS: applied=condition(p,'all') if key not in ('window_motor','door_speaker') else condition(p,entry['condition'])
    else: applied=condition(p,entry['condition'])
    if key=='nut': return [],['fastener_location']
    
    if applied is False:return [],[]
    if applied is None:return [],['applicability:'+entry['condition']]
    if key in SIDE_DOORS:
        if key=='door' and p.get('kind')=='heavy_truck':return [],[]
        doors=p.get('side_doors')
        if doors is None:return [],['side_doors']
        if key in ('door_glass','window_regulator','window_motor','door_speaker','door_hinge'):
            selected=p.get('door_features',{}).get(key)
            if selected is None:return [],['door_features:'+key]
            if not set(selected)<=set(doors): raise ValueError('door feature outside profile')
            doors=selected
        if key=='door_hinge':
            hinges=p.get('hinges_per_door',{})
            return [f'door:{d}:hinge:{i}' for d in doors if type(hinges.get(d)) is int and 1<=hinges[d]<=8 for i in range(1,hinges[d]+1)],[f'hinges:{d}' for d in doors if type(hinges.get(d)) is not int or not 1<=hinges[d]<=8]
        return ['door:'+d for d in doors],[]
    if key=='trunk_lid':
        return {'lid':(['rear:lid'],[]),'liftgate':(['rear:liftgate'],[]),'split':(['rear:door:L','rear:door:R'],[]),'tailgate':(['rear:tailgate'],[]),'none':([],[])}.get(p.get('rear_closure'),([],['rear_closure']))
    if key in AXLE_FEATURES:
        if axles is None:return [],['axles']
        out=[]; missing=[]; feature=AXLE_FEATURES[key]
        for i,a in enumerate(axles,1):
            prefix=f'axle:{i}'
            v=a.get(feature)
            if v is None:missing.append(prefix+':'+feature);continue
            if v is False:continue
            if v is not True:raise ValueError('axle feature must be boolean')
            if key in ('wheel','tire'):
                n=a.get('wheel_count_per_side')
                if n is None:missing.append(prefix+':wheel_count_per_side');continue
                out.extend(f'{prefix}:{s}:wheel:{j}' for s in SIDES for j in range(1,n+1))
            elif key in ('cv_joint','cv_boot','arm','ball_joint','shock','spring','air_spring','leaf_spring','stabilizer_bush','brake_hose','steering_rod','steering_end'):
                n=a.get('per_side',{}).get(key)
                if type(n) is not int or not 1<=n<=16:missing.append(prefix+':count:'+key);continue
                out.extend(f'{prefix}:{s}:{j}' for s in SIDES for j in range(1,n+1))
            elif key in ('brake_pad','brake_shoe','differential','subframe','stabilizer'):out.append(prefix)
            else:out.extend(f'{prefix}:{s}' for s in SIDES)
        return out,missing
    if key in COUNTS:
        field=COUNTS[key]
        if field not in count:return [],['count:'+field]
        return [f'unit:{i}' for i in range(1,count[field]+1)],[]
    if key in ('headlamp','taillamp','foglamp','mirror','cab_mirror','fender','bumper','bumper_cover','bumper_carrier','front_seat','cab_door'):
        known=p.get('positions',{}).get(key)
        if known is not None:
            if len(known)!=len(set(known)) or not all(isinstance(x,str) and x for x in known):raise ValueError('duplicate/invalid positions')
            return list(known),[]
        return [],['positions:'+key]
    if hint=='single':return ['unit:1'],[]
    return [],['unsupported_placement:'+hint]

def preview(entries,profile,source_rows=(),existing_rows=(),*,identity=None,position_evidence=()):
    """Proposals only. Source rows preserved; unresolved generic source is not materialized twice."""
    validate_profile(profile)
    source_rows=list(source_rows); existing_rows=list(existing_rows)
    by_prd=defaultdict(list)
    for row in source_rows:by_prd[row.get('product_id')].append(row)
    present={(r.get('master_key'),r.get('placement')) for r in existing_rows if r.get('master_key') and r.get('placement')}
    generic={r.get('master_key') for r in existing_rows if r.get('master_key') and not r.get('placement')}
    existing_prds={r.get('product_id') for r in existing_rows if r.get('product_id') is not None}
    protected_unknown=any(not r.get('master_key') and r.get('product_id') is None for r in existing_rows)
    ev=defaultdict(set)
    if identity and all(identity.get(k) is not None for k in ('kind','manufacturer_id','model_id','car_id','snapshot_sha')):
        for e in position_evidence:
            if e.get('identity')!=identity or not e.get('master_key') or not e.get('placement') or e.get('placement_verified') is not True:continue
            pid=e.get('product_id'); code=e.get('oem')
            if not isinstance(code,str) or not code.strip() or len(code)>150:continue
            # The normalized position proof must refer to an offer actually present in the pinned graph.
            if any(o.get('supplier_id')==e.get('supplier_id') and o.get('article_nr')==e.get('article_number') and code in o.get('oem_numbers',[]) and e['placement'] in o.get('verified_placements',[]) for r in by_prd.get(pid,[]) for o in r.get('articles',[]) if o.get('supplier_id') and o.get('article_nr')):
                ev[(e['master_key'],e['placement'],pid)].add(code)
    positions=[]; review=[]; excluded=[]; mapped=set()
    for entry in entries:
        key=entry['key']; source_ids=sorted(set(entry['prd_ids'])&by_prd.keys()); mapped.update(source_ids)
        places,missing=placements(entry,profile)
        if missing:review.append({'master_key':key,'reasons':missing,'source_ids':source_ids})
        if not places and not missing:
            excluded.append(key)
            if source_ids:review.append({'master_key':key,'reasons':['source_profile_conflict'],'source_ids':source_ids})
        for place in places:
            marker=(key,place)
            codes=sorted({code for pid in source_ids for code in ev[(key,place,pid)]})
            blocked=protected_unknown or key in generic or bool(set(entry['prd_ids']) & existing_prds) or bool(source_ids) or marker in present
            positions.append(dict(master_key=key,placement=place,name_uk=entry['name_uk'],category_path=entry['category_path'],candidate_prd_ids=entry['prd_ids'],source_ids=source_ids,origin='construction_preview',state='existing' if marker in present else 'reconcile' if blocked else 'supplement_candidate',oem_candidates=codes,proposed_oem=codes[0] if len(codes)==1 else None,oem=None,article=None,fitment_verified=False))
    assert len({(r['master_key'],r['placement']) for r in positions})==len(positions)
    return {'version':VERSION,'source_rows':source_rows,'existing_rows':existing_rows,'positions':positions,'review':review,'excluded':excluded,'unmapped_source_ids':sorted(pid for pid in by_prd if pid is not None and pid not in mapped),'counts':dict(Counter(r['state'] for r in positions))}
