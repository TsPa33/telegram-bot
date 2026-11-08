"""Offline explicit review, no network. Never infer fitment from OEM crosses."""
import argparse,json,os
from pathlib import Path
from volvo_contract import validate,digest,encode


def main():
    p=argparse.ArgumentParser()
    p.add_argument('snapshot');p.add_argument('--mapping',required=True);p.add_argument('--reviewed-by',required=True)
    p.add_argument('--confirm-source-links-and-completeness',action='store_true')
    a=p.parse_args()
    if not a.confirm_source_links_and_completeness:p.error('Explicit source relationship/completeness review required')
    path=Path(a.snapshot);old=json.loads(path.read_text('utf-8'));data=validate(old['payload'])
    if old['sha256']!=digest(data):raise ValueError('Checksum mismatch')
    mapping=json.loads(Path(a.mapping).read_text('utf-8'))
    for row in data['categories']:
        approved=mapping[str(row['product_id'])]
        # Mapping can supply taxonomy only; cannot modify identities or article links.
        for key in ('name_uk','category_path'):
            row[key]=approved[key]
        row['mapping_reviewed_by']=a.reviewed_by
    data['coverage']='complete_verified';data['reviewed_by']=a.reviewed_by
    validate(data)
    temporary=path.with_suffix('.review.tmp');temporary.write_bytes(encode(dict(payload=data,sha256=digest(data))))
    os.replace(temporary,path)
    print('Reviewed locally; upload remains an explicit separate operation.')


if __name__=='__main__':main()
