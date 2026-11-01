"""Import preflight should not silently publish Russian-language category names."""
from app.services.catalogue_language_gate import needs_ukrainian_review

def test_language_gate_detects_russian_category_names():
    for name in ['Двигатель', 'Электрика', 'Подвеска / амортизация',
                 'Тормозная система', 'Рулевое управление', 'Главная передача']:
        assert needs_ukrainian_review(name), name

def test_language_gate_accepts_ukrainian_category_names():
    for name in ['Двигун', 'Електрика', 'Підвіска', 'Гальмівна система',
                 'Кермове управління', 'Головна передача', 'Кузов']:
        assert not needs_ukrainian_review(name), name

def test_import_planner_uses_gate_in_preview_and_resolution():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'app/services/catalogue_import.py').read_text()
    assert "needs_ukrainian_review(name)" in source
    assert "needs_ukrainian_review(new)" in source
    assert "result['unresolved_total']" in source
