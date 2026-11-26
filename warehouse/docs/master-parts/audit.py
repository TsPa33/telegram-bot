"""Reproducible PRD inventory and synthetic profile acceptance, standard library."""
import csv, hashlib, json, sys, re, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"backend"))
from app.services.master_parts_preview import read_seed, preview
ROOT=Path(__file__).resolve().parent

def norm(s):return ' '.join(unicodedata.normalize('NFKC',s).casefold().split())
def semantic(r):return tuple(norm(r[k]) for k in ('assemblygroupdescription','description','normalizeddescription','usagedescription'))
def inventory(path,entries):
    with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    ids={int(r['id']):r for r in rows};assert len(ids)==len(rows)==26938
    direct={pid:e['key'] for e in entries for pid in e['prd_ids']}; assert set(direct)<=ids.keys()
    signatures=defaultdict(set)
    for pid,key in direct.items():signatures[semantic(ids[pid])].add(key)
    descriptions=defaultdict(set)
    for pid,key in direct.items():
        r=ids[pid];descriptions[(norm(r['assemblygroupdescription']),norm(r['description']))].add(key)
    counts=Counter();out=[]
    for r in rows:
        pid=int(r['id']); sig=semantic(r); group,desc,_,_=sig; key=''; reason=''
        if pid in direct:status='seed_candidate';key=direct[pid];reason='original_or_explicit_seed_candidate'
        elif re.search(r'инструмент|оснащение сто|защитная одежда|химические продукт|werkzeug|bekleidung',group):status='likely_non_part';reason='assembly_group'
        elif len(signatures.get(sig,()))==1 and group:status='exact_signature_candidate';key=next(iter(signatures[sig]));reason='same_full_source_signature_not_fitment'
        elif descriptions.get((group,desc)) and group:status='review_same_description';reason='same_group_description_but_other_fields_or_collision'
        elif group:status='review_categorized';reason='unmapped_group'
        else:status='review_uncategorized';reason='no_source_group'
        counts[status]+=1;out.append({**r,'triage_v02':status,'candidate_master_key':key,'reason':reason})
    with (ROOT/'prd_inventory_v02.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
    return dict(counts),hashlib.sha256(path.read_bytes()).hexdigest()

def axle(*,driven=False,steered=False,disc=True,dual=False,air=False,leaf=False,coil=True,independent=True):
    return {'driven':driven,'steered':steered,'wheel_count_per_side':2 if dual else 1,'disc_brakes':disc,'drum_brakes':not disc,'air_suspension':air,'leaf_spring':leaf,'coil_spring':coil,'independent_suspension':independent,'hydraulic_brakes':not (air or leaf),'spring_brake':air,'hub':True,'wheel':True,'shock':True,'halfshaft':driven,'cv_joint':driven and independent,'subframe':independent,'knuckle':steered,'stabilizer':True,'ball_joint':independent,'rack_steering':steered and independent,'abs':True,'per_side':{'shock':1,'spring':1,'arm':2,'ball_joint':1,'air_spring':1,'leaf_spring':1,'brake_hose':1,'stabilizer_bush':1,'steering_rod':1,'steering_end':1,'cv_joint':2,'cv_boot':2}}

def fixture(body='suv',kind='passenger',powertrain='ICE',doors=('FL','FR','RL','RR'),rear='liftgate',axles=None):
    truck=kind=='heavy_truck'; engine=powertrain!='BEV';doors=list(doors)
    p={'kind':kind,'body':body,'powertrain':powertrain,'fuel':'diesel' if truck else 'petrol' if engine else 'electric','transmission':'manual' if truck else 'automatic' if engine else None,'side_doors':doors,'rear_closure':rear,'axles':axles or [axle(driven=True,steered=True),axle(driven=True)],'door_features':{key:doors for key in ('door_glass','window_regulator','window_motor','door_speaker','door_hinge')},'hinges_per_door':{d:2 for d in doors},'positions':{key:['L','R'] for key in ('headlamp','taillamp','foglamp','mirror','cab_mirror','fender','front_seat','cab_door')},'flags':{'low_voltage_battery':True,'turbo':engine,'direct_injection':engine,'injection':engine,'liquid_cooling':True,'hood':not truck,'grille':True,'rear_glass':not truck,'fixed_roof':True,'airbag':not truck,'ac':True,'liquid_heater':engine,'power_windows':True,'door_speaker':True,'air_brakes':truck,'tilting_cab':truck,'hydraulic_brakes':not truck,'abs':True,'trunk_strut':rear=='liftgate','cabin_filter':True,'foglamp':True,'parking_sensor':not truck,'power_seat':False,'catalyst':engine,'lambda':engine,'dpf':truck,'transfer_case':False,'torque_converter':False},'counts':{'cylinders':6 if truck else 4,'spark_plugs':4,'ignition_coils':4,'glow_plugs':6 if truck else 0,'injectors':6 if truck else 4,'intake_valves':8,'exhaust_valves':8,'camshafts':2,'cylinder_heads':1,'valve_covers':1,'engine_mounts':3,'radiator_fans':1,'lambda_sensors':2,'trunk_struts':2,'wipers':2,'parking_sensors':8,'airbags':6,'seatbelts':2 if truck else 5,'seat_frames':2,'rear_seat_assemblies':0 if truck else 1,'traction_motors':1,'traction_inverters':1,'hv_batteries':1,'fuse_boxes':1,'rear_fog_lamps':1,'propshafts':1,'head_bolt_sets':1,'piston_ring_sets':6 if truck else 4}}
    for key in ('bumper','bumper_cover','bumper_carrier'):p['positions'][key]=['front','rear']
    return p

def main():
    path=Path(sys.argv[1]); entries=read_seed(ROOT.parents[1]/'backend/app/data/master_parts_seed_v02.tsv'); triage,sha=inventory(path,entries)
    controls=json.loads((ROOT/'controls.json').read_text()); scenarios=[('Audi Q5 source IDs + illustrative SUV profile',fixture(),controls[0]['source_ids']),('Volvo XC90 source IDs + illustrative SUV profile',fixture(),controls[1]['source_ids']),('synthetic sedan',fixture('sedan',rear='lid'),[]),('synthetic coupe',fixture('coupe',doors=('FL','FR'),rear='lid'),[]),('synthetic 3-door hatch',fixture('hatch',doors=('FL','FR')),[]),('synthetic LCV van',fixture('van','lcv',doors=('FL','FR','SR'),rear='split'),[]),('synthetic tractor 4x2',fixture('tractor','heavy_truck',doors=('FL','FR'),rear='none',axles=[axle(steered=True,disc=True,coil=False,leaf=True,independent=False),axle(driven=True,disc=False,dual=True,air=True,coil=False,independent=False)]),[]),('synthetic tractor 6x4',fixture('tractor','heavy_truck',doors=('FL','FR'),rear='none',axles=[axle(steered=True,coil=False,leaf=True,independent=False),axle(driven=True,disc=False,dual=True,air=True,coil=False,independent=False),axle(driven=True,disc=False,dual=True,air=True,coil=False,independent=False)]),[]),('synthetic BEV',fixture(powertrain='BEV'),[]),('synthetic PHEV',fixture(powertrain='PHEV'),[]),('unknown profile',{},[])]
    summary=[]
    for i,(label,p,ids) in enumerate(scenarios):
        r=preview(entries,p,[{'product_id':pid} for pid in ids]); positions=r['positions']; c=Counter(x['master_key'] for x in positions)
        summary.append({'scenario':label,'source_types':len(ids),'mapped_source_types':len(ids)-len(r['unmapped_source_ids']),'physical_candidates':len(positions),'candidate_types':len(c),'review_types':len({x['master_key'] for x in r['review']}),'excluded_types':len(r['excluded']),'states':r['counts'],'door':c['door'],'cab_door':c['cab_door'],'rear_closure':c['trunk_lid'],'wheel':c['wheel'],'brake_disc':c['brake_disc'],'brake_drum':c['brake_drum'],'brake_pad_set':c['brake_pad'],'brake_shoe_set':c['brake_shoe'],'OEM_proposed':sum(bool(x['proposed_oem']) for x in positions)})
        (ROOT/f'preview_{i:02}.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'source_sha256':sha,'seed_types':len(entries),'seed_prd_ids':sum(len(e['prd_ids']) for e in entries),'triage':triage,'profiles':summary,'scope':'offline synthetic profiles, not live coverage or production fitment'}
    (ROOT/'audit_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
