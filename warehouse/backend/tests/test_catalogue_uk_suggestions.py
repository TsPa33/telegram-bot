from app.services.catalogue_uk_suggestions import ukrainian_name_proposal

def test_known_ukrainian_suggestions():
    assert ukrainian_name_proposal('Рулевое управление') == 'Кермове управління'
    assert ukrainian_name_proposal('Привід колеса') == 'Привід коліс'
    assert ukrainian_name_proposal('Комплектующие') == 'Комплектувальні'

def test_unknown_names_are_not_fabricated():
    assert ukrainian_name_proposal('Редуктор 4x4 OEM 123') is None

def test_preview_marks_suggestions_as_unapproved():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'app/services/catalogue_import.py').read_text()
    assert "['suggested_uk_name']=proposal" in source
    assert "['suggestion_status']='requires_admin_approval'" in source
