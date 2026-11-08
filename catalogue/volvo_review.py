"""Offline reviews. Neither translation nor PDS/link coverage proves a full car catalogue."""
import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from volvo_contract import validate, digest, encode, source_fingerprint, KINDS


def review_taxonomy(payload, mapping, reviewer):
    data = copy.deepcopy(validate(payload))
    if not reviewer.strip() or set(mapping) != {str(r['product_id']) for r in data['categories']}:
        raise ValueError('Review must cover exactly every product ID')
    for row in data['categories']:
        approved = mapping[str(row['product_id'])]
        if approved.get('kind') not in KINDS:
            raise ValueError('Explicit kind required for each product')
        for key in ('name_uk', 'category_path', 'kind'):
            row[key] = approved[key]
        row['mapping_reviewed_by'] = reviewer
    data['taxonomy_status'] = 'reviewed'
    data['taxonomy_reviewed_at'] = datetime.now(timezone.utc).isoformat()
    # Critically: never promote coverage here.
    return validate(data)


def review_coverage(payload, reviewer, reference, confirm):
    data = copy.deepcopy(validate(payload))
    if not confirm or not reviewer.strip() or not reference.strip() or data.get('collection_complete') is not True:
        raise ValueError('Separate vehicle-catalogue completeness evidence required')
    data['coverage_evidence'] = dict(scope='vehicle_part_types', reviewed_by=reviewer,
        reference=reference, reviewed_at=datetime.now(timezone.utc).isoformat(),source_fingerprint=source_fingerprint(data))
    data['coverage'] = 'complete_verified'
    return validate(data)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('snapshot')
    p.add_argument('--review', choices=('taxonomy', 'coverage'), required=True)
    p.add_argument('--mapping')
    p.add_argument('--reviewed-by', required=True)
    p.add_argument('--coverage-reference')
    p.add_argument('--confirm-vehicle-catalogue-completeness', action='store_true')
    a = p.parse_args()
    path = Path(a.snapshot)
    old = json.loads(path.read_text('utf-8'))
    if old['sha256'] != digest(old['payload']):
        raise ValueError('Checksum mismatch')
    if a.review == 'taxonomy':
        if not a.mapping or a.confirm_vehicle_catalogue_completeness or a.coverage_reference:
            p.error('Taxonomy review cannot approve coverage')
        data = review_taxonomy(old['payload'], json.loads(Path(a.mapping).read_text('utf-8')), a.reviewed_by)
    else:
        if a.mapping:
            p.error('Coverage review must be separate from taxonomy')
        data = review_coverage(old['payload'], a.reviewed_by, a.coverage_reference or '', a.confirm_vehicle_catalogue_completeness)
    temporary = path.with_suffix('.review.tmp')
    temporary.write_bytes(encode(dict(payload=data, sha256=digest(data))))
    os.replace(temporary, path)
    print(f'{a.review} reviewed locally; coverage={data["coverage"]}; no upload performed')


if __name__ == '__main__':
    main()
