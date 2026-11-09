"""SELECT-only, exact Volvo 107555 type-gap diagnostic. Prints no raw source rows."""
import argparse
import json
import os
from pathlib import Path

from volvo_vehicle_import import connection, read, bounded, value, import_summary
from volvo_contract import validate, digest, MAX_BYTES

CAR, MODEL = 107555, 13084


def ids(rows, field='productid'):
    return {int(value(r, field)) for r in rows if value(r, field) is not None and int(value(r, field)) > 0}


def columns(source, table):
    # Names are internal constants, never user SQL identifiers.
    return {r['column_name'].lower(): r['column_name'] for r in read(source,
        'SELECT COLUMN_NAME AS column_name FROM information_schema.COLUMNS '
        'WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s', (table,))}


def snapshot_check(path, expected_sha):
    if not path:
        return None
    if not expected_sha or len(expected_sha) != 64 or any(c not in '0123456789abcdef' for c in expected_sha):
        raise ValueError('Expected canonical snapshot SHA-256 is required')
    with Path(path).open('rb') as stream:
        raw = stream.read(2 * MAX_BYTES + 1)
    if len(raw) > 2 * MAX_BYTES:
        raise ValueError('Snapshot file exceeds bound')
    envelope = json.loads(raw.decode('utf-8-sig'))
    data = validate(envelope['payload'])
    if data['car_id'] != CAR or data['model_id'] != MODEL:
        raise ValueError('Snapshot identity mismatch')
    if envelope['sha256'] != expected_sha or digest(data) != expected_sha:
        raise ValueError('Snapshot checksum mismatch')
    return envelope


def audit(source, snapshot=None):
    car = bounded(source, 'passanger_cars', 'id=%s', (CAR,))
    model = bounded(source, 'models', 'id=%s', (MODEL,))
    if len(car) != 1 or int(value(car[0], 'modelid')) != MODEL or len(model) != 1 or int(value(model[0], 'manufacturerid')) != 120:
        raise ValueError('Exact Volvo source identity mismatch')
    link_rows = read(source, 'SELECT DISTINCT productid FROM article_links '
        'WHERE linkageid=%s AND linkagetypeid=2 ORDER BY productid LIMIT 20001', (CAR,))
    if len(link_rows) > 20000:
        raise ValueError('Type bound exceeded; refusing incomplete report')
    linked = ids(link_rows)
    pds = bounded(source, 'passanger_car_pds', 'passangercarid=%s', (CAR,))
    trees = bounded(source, 'passanger_car_trees', 'passangercarid=%s', (CAR,))
    pds_columns = columns(source, 'passanger_car_pds')
    tree_columns = columns(source, 'passanger_car_trees')
    if 'productid' not in pds_columns:
        raise ValueError('PDS productid column missing')
    pds_ids = ids(pds)
    tree_ids = ids(trees) if 'productid' in tree_columns else set()
    missing = pds_ids - linked
    candidates = missing | (tree_ids - linked)
    details = []
    for product in sorted(candidates):
        prd = bounded(source, 'prd', 'id=%s', (product,))
        rows = [r for r in pds if value(r, 'productid') is not None and int(value(r, 'productid')) == product]
        suppliers = ids(rows, 'supplierid') if 'supplierid' in pds_columns else set()
        # A PDS supplier/type pair is NOT an exact article. Only a direct number
        # column on that exact car/type row can substantiate an article join.
        number_field = next((k for k in ('datasupplierarticlenumber',) if k in pds_columns), None)
        exact_articles = set()
        if number_field and 'supplierid' in pds_columns:
            for row in rows:
                supplier, number = value(row, 'supplierid'), value(row, number_field)
                if supplier is not None and number:
                    matches = bounded(source, 'articles', 'supplierId=%s AND DataSupplierArticleNumber=%s', (supplier, number))
                    if matches:
                        exact_articles.add((int(supplier), str(number)))
        details.append(dict(product_id=product, in_pds=product in pds_ids,
            direct_tree_product_link=product in tree_ids, prd_rows=len(prd), pds_rows=len(rows),
            supplier_count=len(suppliers), confirmed_exact_articles=len(exact_articles),
            confirmed_type_candidate=len(prd) == 1 and (product in pds_ids or product in tree_ids),
            needs_article_verification=not bool(exact_articles),
            reason='exact_car_type_relation_and_prd' if len(prd) == 1 else 'missing_or_ambiguous_prd'))
    confirmed = [r for r in details if r['confirmed_type_candidate']]
    result = dict(car_id=CAR, model_id=MODEL, mode='read_only',
        article_links_types=len(linked), article_links_product_ids=sorted(linked),
        pds_rows=len(pds), pds_types=len(pds_ids), pds_columns=sorted(pds_columns),
        pds_repeated_product_rows=sum(value(r,'productid') is not None for r in pds)-len({value(r,'productid') for r in pds if value(r,'productid') is not None}),
        pds_only_product_ids=sorted(missing), article_links_only_product_ids=sorted(linked-pds_ids),
        tree_rows=len(trees), tree_columns=sorted(tree_columns),
        tree_assessment='direct_productid_column_present' if 'productid' in tree_columns else 'no_direct_productid_column; node IDs are not product IDs',
        tree_only_product_ids=sorted(tree_ids-linked), additional_candidates=len(details),
        confirmed_type_candidates=len(confirmed),
        candidates_with_exact_articles=sum(r['confirmed_exact_articles'] > 0 for r in confirmed),
        candidates_needing_clarification=sum(not r['confirmed_type_candidate'] or r['needs_article_verification'] for r in details),
        candidates=details, snapshot=None,
        notes=['Repeated PDS products can represent different nodes/suppliers, not duplicate parts.',
               'No articles inferred from other cars, names, OEMs or manufacturer alone.',
               'A direct source relation is catalogue evidence, not VIN or physical stock verification.',
               'No direct tree productid does not prove that an indirect tree mapping is impossible.'])
    if snapshot:
        summary = import_summary(snapshot)
        saved = {r['product_id'] for r in snapshot['payload']['categories']}
        result['snapshot'] = dict(summary=summary, missing_link_types=sorted(linked-saved),
            snapshot_only_types=sorted(saved-linked), pds_types_missing_snapshot=sorted(pds_ids-saved))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', help='Existing local full export JSON; never modified')
    parser.add_argument('--expected-sha256', help='Independently verified canonical payload SHA, not file hash')
    args = parser.parse_args()
    try:
        if os.getenv('SOURCE_HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost'):
            raise ValueError('Only local Windows source permitted')
        snapshot = snapshot_check(args.snapshot, args.expected_sha256)
        with connection('SOURCE', 'td1q2018') as source:
            read(source, 'SET SESSION max_execution_time=30000')
            read(source, 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            read(source, 'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            try:
                result = audit(source, snapshot)
            finally:
                source.rollback()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        # Never print connector error messages, credentials or source records.
        print(json.dumps(dict(status='BLOCKED', error_type=type(exc).__name__,
            action='Check local SOURCE_* settings, source schema and snapshot checksum; no import performed.')))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
