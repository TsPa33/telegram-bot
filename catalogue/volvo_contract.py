"""Versioned Volvo export contract; source IDs never mean plan.parts K-Types."""
import hashlib
import json

MAX_BYTES = 8 * 1024 * 1024


def encode(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')


def digest(payload):
    return hashlib.sha256(encode(payload)).hexdigest()


def validate(payload):
    if len(encode(payload)) > MAX_BYTES:
        raise ValueError('Modification snapshot exceeds 8 MiB; split import before publishing')
    if payload.get('schema') != 'carpot.volvo.v1' or payload.get('manufacturer_id') != 120:
        raise ValueError('Not a Volvo integration snapshot')
    for key in ('car_id', 'model_id'):
        if type(payload.get(key)) is not int or payload[key] <= 0:
            raise ValueError('Invalid exact source identity')
    if payload.get('coverage') not in ('partial', 'complete_verified'):
        raise ValueError('Invalid coverage')
    if not payload.get('observed_at') or not isinstance(payload.get('categories'), list) or not isinstance(payload.get('articles'),dict):
        raise ValueError('Missing observation/categories')
    ids = set()
    for row in payload['categories']:
        if type(row.get('product_id')) is not int or row['product_id'] <= 0 or row['product_id'] in ids:
            raise ValueError('Invalid/duplicate product identity')
        ids.add(row['product_id'])
        for key in row.get('articles',[]):
            if key not in payload['articles']:raise ValueError('Missing linked article')
        if payload['coverage'] == 'complete_verified' and (
            not row.get('name_uk') or len(row.get('category_path', [])) != 3
            or not row.get('mapping_reviewed_by')
        ):
            raise ValueError('Verified coverage needs reviewed Ukrainian taxonomy')
    if payload['coverage'] == 'complete_verified' and (
        not ids or not payload.get('collection_complete') or not payload.get('reviewed_by')
    ):
        raise ValueError('Verified coverage requires complete collection and explicit review')
    return payload
