from pathlib import Path

def test_carpot_mapping_endpoint_is_owner_only_and_read_only():
    source=(Path(__file__).resolve().parents[1]/'app/api/catalogue.py').read_text()
    start=source.index("@router.get('/admin/audit/carpot-section-mapping')")
    end=source.index("@router.get('/admin/audit/duplicate-review.csv')",start)
    route=source[start:end]
    assert 'owner:Admin' in route
    assert 'audited(log_report=False)' in route
    assert "'legacy_id_preserved':True" in route
    assert "'approval':'pending'" in route
    assert 'db.commit(' not in route
    assert 'db.add(' not in route
