"""Response-only catalogue minimization. Stored evidence and request tokens are unchanged."""
from collections import Counter
from app.services.catalogue_import import platform_admin
TECHNICAL={'baseline_positions','published_reference_positions','exact_source_positions','gaps','source','sources','source_refs','source_ref_count','source_truncated','source_snapshot_sha','rule_evidence','vehicle_provenance','evidence_details','compatible_evidence','reference_prices','provenance'}
def public_payload(value):
    if isinstance(value,list):return [public_payload(v) for v in value]
    if isinstance(value,dict):
        # Keep legacy array shapes without exposing a single private reference.
        return {k:([] if k in TECHNICAL else public_payload(v)) for k,v in value.items() if k not in TECHNICAL or k in {'source','sources','reference_prices','gaps'} and isinstance(v,list)}
    return value

def source_report(rows):
    buckets=Counter();items=[]
    for row in rows:
        refs=(row.plan_v3 or {}).get('snapshot',{}).get('source',[])
        kinds=sorted({r.get('kind','unknown') for r in refs if isinstance(r,dict)})
        bucket=kinds[0] if len(kinds)==1 else 'multiple_sources' if kinds else 'unknown'
        buckets[bucket]+=1;items.append(dict(id=row.id,sources=refs))
    return dict(total=len(rows),counts=dict(buckets),items=items)

def vehicle_payload(value):
    if isinstance(value,list):return [vehicle_payload(v) for v in value]
    if isinstance(value,dict):return {k:public_payload(v) if k=='dismantling_v3' else vehicle_payload(v) for k,v in value.items()}
    return value
