"""Versioned Volvo evidence. Taxonomy review is not vehicle coverage evidence."""
import copy
import hashlib
import json
from pathlib import Path
from datetime import datetime

MAX_BYTES = 8 * 1024 * 1024
KINDS = ('part', 'consumable', 'equipment', 'review')
TAXONOMY_FIELDS = ('name_uk', 'category_path', 'kind', 'mapping_reviewed_by', 'taxonomy_note')


def encode(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')


def digest(payload):
    return hashlib.sha256(encode(payload)).hexdigest()


def source_fingerprint(payload):
    """Coverage approval binds the source graph, independently of translations."""
    raw = copy.deepcopy(payload)
    for key in ('coverage', 'coverage_evidence', 'taxonomy_status', 'taxonomy_reviewed_at', 'reviewed_by'):
        raw.pop(key, None)
    for row in raw.get('categories', []):
        for key in TAXONOMY_FIELDS:
            row.pop(key, None)
    return digest(raw)


def coverage_verified(payload):
    proof = payload.get('coverage_evidence') or {}
    if not isinstance(proof,dict):return False
    return bool(payload.get('coverage') == 'complete_verified'
        and payload.get('collection_complete') is True
        and proof.get('scope') == 'vehicle_part_types'
        and proof.get('reviewed_by') and proof.get('reference')
        and proof.get('source_fingerprint') == source_fingerprint(payload))


def validate(payload):
    if not isinstance(payload, dict) or len(encode(payload)) > MAX_BYTES:
        raise ValueError('Invalid or oversized Volvo snapshot')
    if not ((payload.get('schema') == 'carpot.volvo.v1' and payload.get('manufacturer_id') == 120) or (payload.get('schema') == 'carpot.vehicle.v1' and type(payload.get('manufacturer_id')) is int and payload['manufacturer_id'] > 0)):
        raise ValueError('Not a Volvo integration snapshot')
    for key in ('car_id', 'model_id'):
        if type(payload.get(key)) is not int or payload[key] <= 0:
            raise ValueError('Invalid exact source identity')
    if payload.get('coverage') not in ('partial', 'complete_verified'):
        raise ValueError('Invalid coverage')
    if not isinstance(payload.get('observed_at'),str):raise ValueError('Missing observation timestamp')
    datetime.fromisoformat(payload['observed_at'].replace('Z', '+00:00'))
    if payload.get('taxonomy_status','unreviewed') not in ('unreviewed','draft','reviewed'):raise ValueError('Invalid taxonomy status')
    if not isinstance(payload.get('categories'), list) or not isinstance(payload.get('articles'), dict):
        raise ValueError('Missing categories/articles')
    ids = set()
    for row in payload['categories']:
        if type(row.get('product_id')) is not int or row['product_id'] <= 0 or row['product_id'] in ids:
            raise ValueError('Invalid/duplicate product identity')
        ids.add(row['product_id'])
        if row.get('kind', 'review') not in KINDS:
            raise ValueError('Invalid part kind')
        if not isinstance(row.get('articles', []), list) or len(set(row.get('articles', []))) != len(row.get('articles', [])):
            raise ValueError('Duplicate article link')
        for key in row.get('articles', []):
            if key not in payload['articles']:
                raise ValueError('Missing linked article')
        if payload.get('taxonomy_status') == 'reviewed' and (
            not row.get('name_uk') or len(row.get('category_path', [])) != 3
            or not row.get('mapping_reviewed_by') or 'kind' not in row
        ):
            raise ValueError('Reviewed taxonomy requires names, paths, kind and reviewer')
        if payload.get('taxonomy_status')=='reviewed':
            taxonomy=json.loads(Path(__file__).with_name('carpot_taxonomy.json').read_text('utf-8'))
            path=row['category_path']
            if path[0] not in taxonomy or path[1] not in taxonomy[path[0]] or any(not isinstance(v,str) or not 1<=len(v)<=100 for v in path):
                raise ValueError('Taxonomy path must use existing CarPot sections/subsections')
    for key, article in payload['articles'].items():
        if (type(article.get('supplier_id')) is not int or article['supplier_id'] <= 0
            or not isinstance(article.get('article_number'), str)
            or key != f"{article['supplier_id']}:{article['article_number']}"
            or article.get('car_id', payload['car_id']) != payload['car_id']):
            raise ValueError('Article source identity mismatch')
    if payload['coverage'] == 'complete_verified' and (not ids or not coverage_verified(payload)):
        raise ValueError('Complete vehicle coverage requires separate source-bound evidence; translation is insufficient')
    return payload


def compact_plan(payload, snapshot_sha):
    validate(payload)
    rows = []
    for row in payload['categories']:
        # No raw prd records, supplier lists, article identities, OEMs or photos.
        item = {key: row[key] for key in ('product_id', *TAXONOMY_FIELDS) if key in row}
        original = row.get('original') or []
        labels = {str(k).casefold(): v for r in original for k, v in r.items()}
        item['name_source'] = row.get('name_source') or labels.get('description') or labels.get('normalizeddescription') or ''
        if len(original)==1:
            normalized={str(k).casefold():v for k,v in original[0].items()}
            item['source_prd_sha256']=digest({k:normalized.get(k) for k in ('id','assemblygroupdescription','description','normalizeddescription','usagedescription')})
        item['article_count'] = len(row.get('articles', []))
        item['kind'] = row.get('kind','review')
        rows.append(item)
    return dict(schema='carpot.volvo.plan.v2' if payload['schema']=='carpot.volvo.v1' else 'carpot.vehicle.plan.v1', manufacturer_id=payload['manufacturer_id'],
        car_id=payload['car_id'], model_id=payload['model_id'],
        modification=payload.get('modification', {}), observed_at=payload['observed_at'],
        source_snapshot_sha=snapshot_sha, coverage=payload['coverage'],
        coverage_verified=coverage_verified(payload), taxonomy_status=payload.get('taxonomy_status', 'unreviewed'),
        categories=rows, photos=payload.get('image_status','metadata_only'))
