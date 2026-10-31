"""No-write catalogue normalization review contract."""
from pathlib import Path
import ast
import json
import re

APP=Path(__file__).resolve().parents[1]/'app'
DATA=APP/'data'/'catalogue_ua_proposals_v1.json'
AUDIT=APP/'catalogue_audit_once.py'
ROUTE=APP/'api'/'catalogue.py'
REGISTRY=APP/'route_registry.py'

def norm(s):
    return ' '.join(re.sub(r'[^\w]+',' ',s.casefold()).split())

def test_ukrainian_proposals_are_explicit_and_approval_gated():
    p=json.loads(DATA.read_text(encoding='utf8'))
    assert p['version']=='carpot.catalogue.ua.proposals.v1'
    assert p['translation_proposals'] and p['hierarchy_review']
    for section in ('translation_proposals','hierarchy_review'):
        for item in p[section]:
            assert item['source'].strip() and item['target'].strip()
            assert item['approval']=='manual'
        keys=[norm(v['source']) for v in p[section]]
        assert len(keys)==len(set(keys)), section

def test_dup_review_requires_live_stock_and_tree_reference_assessment():
    source=AUDIT.read_text(encoding='utf8')
    ast.parse(source)
    assert "SET TRANSACTION READ ONLY" in source
    assert 'reference_rows=query("category_stock_refs"' in source
    assert 'child_links=Counter(' in source
    assert 'risk="linked_stock"' in source
    assert 'risk="has_children"' in source
    assert 'risk="cross_source"' in source
    assert 'risk="unreferenced_candidate"' in source
    assert '"action":"review_only_no_merge"' in source
    assert 'for key,values in seen.items():' in source
    assert 'row["pid"]' in source
    assert 'norm(row["o"])' in source
    assert 'connection.rollback()' in source
    for forbidden in ('UPDATE categories SET','DELETE FROM categories','DROP TABLE categories',
                      'connection.commit()','db.commit()','db.add('):
        assert forbidden not in source

def test_review_export_is_platform_admin_only_and_csv_formula_guarded():
    c=ROUTE.read_text(encoding='utf8')
    ast.parse(c)
    assert "def catalogue_duplicate_review_csv(db:DB,owner:Admin):" in c
    assert "GET /api/v1/catalogue/admin/audit/duplicate-review.csv" not in c
    assert "value.lstrip().startswith(('=', '+', '-', '@'))" in c
    registry=REGISTRY.read_text(encoding='utf8')
    assert "('GET', '/api/v1/catalogue/admin/audit/duplicate-review.csv')" in registry
