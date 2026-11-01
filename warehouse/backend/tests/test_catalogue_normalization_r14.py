"""R14 catalogue terminology review is admin-only and read-only."""
import os
from pathlib import Path
import pytest
from app.db import engine
from sqlalchemy import text

def test_proposals_require_platform_owner(logged,monkeypatch):
    url='/api/v1/catalogue/admin/audit/name-proposals'
    assert logged.get(url).status_code==403
    owner=logged.get('/api/v1/auth/me').json()
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner['id'])
    r=logged.get(url)
    assert r.status_code==200,r.text
    j=r.json()
    assert j['total']==73
    assert j['status']=='pending_manual_review'
    assert all(row['approval']=='pending' for row in j['items'])
    assert len([r for r in j['items'] if r['type']=='translation'])==58
    assert len([r for r in j['items'] if r['type']=='hierarchy'])==15
    monkeypatch.delenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS')
    assert logged.get(url).status_code==403

def test_paginated_duplicate_review_is_read_only_and_owner_only(logged,monkeypatch):
    url='/api/v1/catalogue/admin/audit/duplicate-groups?limit=2&offset=0'
    assert logged.get(url).status_code==403
    owner=logged.get('/api/v1/auth/me').json()
    monkeypatch.setenv('WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS',owner['id'])
    monkeypatch.setenv('WAREHOUSE_ENV','staging')
    with engine().connect() as conn:
        initial=conn.execute(text("SELECT count(*) FROM categories")).scalar_one()
    r=logged.get(url)
    assert r.status_code==200,r.text
    body=r.json()
    assert body['total']==0
    assert body['items']==[]
    assert 'risk_counts' in body
    with engine().connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM categories")).scalar_one()==initial
    assert logged.get('/api/v1/catalogue/admin/audit/duplicate-groups?limit=1000').status_code==422

def test_auditor_only_selects_and_normalization_never_merges():
    app=Path(__file__).resolve().parents[1]/'app'
    source=(app/'catalogue_audit_once.py').read_text()
    assert 'def audited(*, log_report=True):' in source
    assert 'SET TRANSACTION READ ONLY' in source
    assert '"action":"review_only_no_merge"' in source
    assert "if log_report:" in source
    cat=(app/'api'/'catalogue.py').read_text()
    assert "def catalogue_duplicate_groups(" in cat
    assert "def catalogue_name_proposals(" in cat
    assert "return {k:v for k,v in stats.items() if k!='duplicate_review_all'}" in cat


def test_csv_export_safely_escapes_spreadsheet_formulas():
    import csv
    import io
    from app.api.catalogue import csv_safe_cell
    cases = {
        '=HYPERLINK("https://example.test", "click")': "'=HYPERLINK(\"https://example.test\", \"click\")",
        ' +SUM(1,2)': "' +SUM(1,2)",
        '\\t@SUM(1,2)': "'\\t@SUM(1,2)",
        '-3+5': "'-3+5",
        'Фара права': 'Фара права',
        '123456': '123456',
        None: '',
    }
    for original, expected in cases.items():
        assert csv_safe_cell(original) == expected
    for original, expected in cases.items():
        out = io.StringIO(newline='')
        csv.writer(out).writerow([csv_safe_cell(original)])
        assert next(csv.reader(io.StringIO(out.getvalue())))[0] == expected


def test_both_review_exports_use_csv_sanitization():
    source = (Path(__file__).resolve().parents[1] / 'app' / 'api' / 'catalogue.py').read_text()
    mapping = source.split("@router.get('/admin/audit/catalogue-mapping.csv')", 1)[1].split("@router.get('/admin/audit/duplicate-review.csv')", 1)[0]
    duplicates = source.split("@router.get('/admin/audit/duplicate-review.csv')", 1)[1].split("@router.get('/admin/audit/duplicate-groups')", 1)[0]
    assert 'writer.writerow([csv_safe_cell(row.get(k' in mapping
    assert 'writer.writerow([csv_safe_cell(v)' in duplicates
