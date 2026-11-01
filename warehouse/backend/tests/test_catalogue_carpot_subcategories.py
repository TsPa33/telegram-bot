from app.services.catalogue_carpot_sections import SECTIONS, SUBCATEGORIES, propose_subcategory

def test_every_section_has_unique_subcategories():
    assert len(SECTIONS)==12 == len(SUBCATEGORIES)
    for group in SUBCATEGORIES:
        assert len(group)>0
        assert len({x[0] for x in group})==len(group)

def test_steering_subgroup():
    v=propose_subcategory('Кермове управління','Кермове управління','Кермова рейка','Кермова рейка')
    assert v['subcategory']=='Кермовий механізм'

def test_uncertain_subsection_requires_review():
    v=propose_subcategory('Гальмівна система','Гальмівна система','', 'Невідома деталь')
    assert v['status']=='review_required'
