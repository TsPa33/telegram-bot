from app.services.catalogue_carpot_sections import SECTIONS, propose_section

def test_twelve_sections():
    assert len(SECTIONS)==12
    assert len(set(SECTIONS))==12

def test_known_part_classification():
    result=propose_section('Рулевое управление','Кермова рейка','Рулевая рейка')
    assert result['section']=='Кермове управління'
    assert result['status']=='suggested'

def test_ambiguous_multisystem_needs_review():
    assert propose_section('Підвіска та кермове управління','','')['status']=='review_required'
    assert propose_section('','','Невідома деталь')['section'] is None

def test_never_claim_vehicle_compatibility():
    assert 'fitment' not in propose_section('Кузов','Двері','Двері передні')
