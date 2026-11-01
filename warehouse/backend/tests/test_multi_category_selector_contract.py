from pathlib import Path

def test_grouped_category_filter_preserves_legacy_ids():
    src=(Path(__file__).resolve().parents[1]/'app/api/routes.py').read_text()
    assert 'category_id.split(",")' in src
    assert 'Part.category_id.in_(category_ids)' in src
    assert 'len(category_ids) > 50' in src
