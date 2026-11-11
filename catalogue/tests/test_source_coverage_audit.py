"""Synthetic offline coverage-audit tests; no MySQL/Railway connections."""
import csv
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_coverage_audit as audit


def references():
    return {
        'manufacturers': [
            {'id': 120, 'description': 'VOLVO', 'ispassengercar': 'False'},
            {'id': 120, 'description': 'VOLVO', 'ispassengercar': 'True'},
            {'id': 121, 'description': 'VW', 'ispassengercar': 'True'},
        ],
        'models': [
            {'id': 13084, 'manufacturerid': 120, 'description': 'XC90 II'},
            {'id': 7583, 'manufacturerid': 120, 'description': 'XC60'},
            {'id': 7873, 'manufacturerid': 121, 'description': 'Golf VI'},
        ],
        'prd': [
            {'id': 101, 'description': 'Starter', 'normalizeddescription': '', 'assemblygroupdescription': '', 'usagedescription': ''},
            {'id': 102, 'description': 'Filter', 'normalizeddescription': '', 'assemblygroupdescription': '', 'usagedescription': ''},
            {'id': 103, 'description': 'Brakes', 'normalizeddescription': '', 'assemblygroupdescription': '', 'usagedescription': ''},
        ],
    }


def test_preflight_index_access_fail_closed():
    assert audit.indexed_safely(
        {'PRIMARY': ['id']}, {'idx_linkage': ['linkageid', 'productid']},
        {'PRIMARY': ['id']})
    assert audit.indexed_safely(
        {'PRIMARY': ['id']}, {'idx_pair': ['linkagetypeid', 'linkageid']},
        {'PRIMARY': ['id']})
    assert not audit.indexed_safely(
        {'PRIMARY': ['id']}, {'idx_type': ['linkagetypeid'], 'idx_product': ['productid']},
        {'PRIMARY': ['id']})
    assert not audit.indexed_safely(
        {'idx_model': ['modelid']}, {'idx_pair': ['linkagetypeid', 'linkageid']},
        {'PRIMARY': ['id']})


def test_references_role_isolated_and_checkpoint_bound(tmp_path):
    with sqlite3.connect(tmp_path / 'audit.sqlite3') as db:
        audit.initialize(db)
        refs = references()
        audit.store_references(db, refs)
        assert db.execute('SELECT COUNT(*) FROM makers').fetchone()[0] == 2
        audit.store_references(db, refs)
        assert db.execute('SELECT COUNT(*) FROM prd').fetchone()[0] == 3
        refs['prd'][0]['description'] = 'CHANGED'
        with pytest.raises(RuntimeError, match='NEW --output'):
            audit.store_references(db, refs)
        assert db.execute('SELECT name FROM prd WHERE id=101').fetchone()[0] == 'Starter'


def test_local_only_counts_and_reports(tmp_path):
    with sqlite3.connect(tmp_path / 'audit.sqlite3') as db:
        audit.initialize(db)
        audit.store_references(db, references())
        passenger = {13084, 7583, 7873}
        audit.process_batch(
            db,
            [{'id': 107555, 'modelid': 13084}, {'id': 107556, 'modelid': 13084},
             {'id': 107557, 'modelid': 7873}],
            {107555: {101, 102}, 107556: {101}, 107557: {102, 999}},
            passenger
        )
        with db:
            audit.setmeta(db, 'scan_complete', 1)
        summary = audit.report(db, tmp_path)
        assert summary['complete'] is True
        assert summary['passenger_modifications_with_prd_links'] == 3
        assert summary['passenger_car_prd_link_pairs'] == 5
        assert summary['passenger_brands_with_prd_links'] == 2
        assert summary['passenger_models_with_prd_links'] == 2
        assert summary['prd_source_ids_linked_to_passenger_models'] == 2
        assert summary['linked_ids_missing_from_prd'] == 1
        assert summary['physical_part_types_after_normalization'] is None
        assert summary['new_canonical_types_approved'] == 0
        with (tmp_path / 'by_brand.csv').open(encoding='utf-8-sig', newline='') as stream:
            brands = list(csv.DictReader(stream))
        assert {row['manufacturer_name'] for row in brands} == {'VOLVO', 'VW'}
        with (tmp_path / 'unknown_prd_ids.csv').open(encoding='utf-8-sig', newline='') as stream:
            unknown = list(csv.DictReader(stream))
        assert unknown == [{'product_id': '999'}]
        assert json.loads((tmp_path / 'summary.json').read_text(encoding='utf-8'))['complete']


def test_unverified_model_is_not_counted_as_passenger(tmp_path):
    with sqlite3.connect(tmp_path / 'audit.sqlite3') as db:
        audit.initialize(db)
        audit.store_references(db, references())
        audit.process_batch(
            db, [{'id': 1, 'modelid': 999}, {'id': 2, 'modelid': 13084}],
            {1: {101}, 2: {102}}, {13084, 7583, 7873})
        result = audit.report(db, tmp_path)
        assert not result['complete']
        assert result['car_rows_scanned'] == 2
        assert result['passenger_modifications_scanned'] == 1
        assert result['passenger_car_prd_link_pairs'] == 1
        assert result['prd_source_ids_linked_to_passenger_models'] == 1
