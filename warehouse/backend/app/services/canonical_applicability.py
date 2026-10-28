"""Future generator conditions, deliberately separate from fitment confirmation."""
from app.services.canonical_rules import RULES,TYPES,UNIVERSAL_TYPES
GROUPS={'A':'Загальна конструктивна функція','B':'Залежить від силової установки','C':'Залежить від трансмісії, приводу чи кузова','D':'Залежить від заводських опцій','E':'Недостатньо підтверджених даних'}
POLICIES={tid:r.get('applicability',{'groups':['E'],'required_fields':[]}) for r in RULES['types'] for tid,t in TYPES.items() if (r['name'],r['category'],r['subcategory'])==(t['name'],t['category'],t['subcategory'])}

POLICIES.update({tid:r.get('applicability',{'groups':['E'],'required_fields':[]}) for tid,r in UNIVERSAL_TYPES.items()})

def assess(type_id,query,features=None,configuration=None,provenance=None):
    policy=POLICIES.get(type_id,{'groups':['E'],'required_fields':[]});features=features or {}
    groups=set(policy['groups']);required=set(policy.get('required_fields',[]))
    if features.get('option_labels'):groups.add('D');required.add('options')
    if features.get('fuel_labels'):groups.add('B');required.add('fuel_type')
    if features.get('powertrain_labels'):groups.add('B');required.add('powertrain')
    if features.get('drive_labels'):groups.add('C');required.add('drive')
    if features.get('engine_codes'):groups.add('B');required.add('engine_code')
    known=configuration or query;quality=provenance or {}
    missing=[k for k in sorted(required) if known.get(k) in (None,'') or quality.get(k,{}).get('confidence')!='verified']
    if missing:groups.add('E')
    conflicts=[]
    if known.get('powertrain') and policy.get('powertrains') and known['powertrain'] not in policy['powertrains']:conflicts.append('powertrain')
    if known.get('drive') and policy.get('drives') and known['drive'] not in policy['drives']:conflicts.append('drive')
    for field,labels in [('fuel_type','fuel_labels'),('powertrain','powertrain_labels'),('drive','drive_labels'),('engine_code','engine_codes')]:
        if known.get(field) and features.get(labels) and known[field] not in features[labels]:conflicts.append(field)
    if features.get('option_labels'):
        options=known.get('options')
        if options is not None and not set(features['option_labels'])<=set(options):
            if known.get('options_complete') and quality.get('options_complete',{}).get('confidence')=='verified':conflicts.append('options')
            elif 'options' not in missing:missing.append('options');groups.add('E')
    return {'groups':sorted(groups),'labels':[GROUPS[g] for g in sorted(groups)],'required_fields':sorted(required),
        'missing_or_unverified':missing,'source_constraints':{k:features[k] for k in ('fuel_labels','powertrain_labels','drive_labels','option_labels','engine_codes') if features.get(k)},
        'condition_state':'condition_not_met' if conflicts and not missing else 'needs_evidence' if missing or conflicts else 'condition_met',
        'conflicting_fields':sorted(set(conflicts)),'confirms_fitment':False,'excludes_plan_items':False}
