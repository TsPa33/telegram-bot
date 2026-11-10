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


def test_taxonomy_1_3_preserves_all_legacy_labels_patterns_and_indices():
    import json,hashlib
    from pathlib import Path
    from app.services.catalogue_carpot_sections import SUBCATEGORIES
    baseline=json.loads((Path(__file__).parent/'fixtures/taxonomy_before_1_3.json').read_text())
    assert list(SECTIONS)==baseline['sections']
    prefixes=[list(group[:length]) for group,length in zip(SUBCATEGORIES,baseline['lengths'])]
    assert hashlib.sha256(json.dumps(prefixes,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()==baseline['sha256']
    for group in SUBCATEGORIES:
        assert len({label for label,_ in group})==len(group)


def test_new_paths_are_advisory_and_do_not_infer_positions():
    from app.services.catalogue_carpot_sections import propose_subcategory
    examples=[
        (0,'Датчик температури / тиску оливи','Система змащення'),
        (2,'Важіль підвіски','Важелі та шарніри підвіски'),
        (2,'Сайлентблок балки підвіски','Балка підвіски та її опори'),
        (2,'Стійка стабілізатора','Стабілізатори та їхні стійки'),
        (4,'Вакуумний насос гальмівної системи','Вакуумна система гальм'),
        (5,'Рейлінг даху','Дах та багажні кріплення'),
        (5,'Газовий упор кришки багажника','Багажник та його механізми'),
        (5,'Поріг-підніжка','Пороги та підніжки'),
        (7,'Вимикач ліхтаря заднього ходу','Вимикачі та перемикачі'),
        (8,'Лампа покажчика повороту','Сигнальне та допоміжне освітлення'),
    ]
    for section,name,expected in examples:
        result=propose_subcategory(SECTIONS[section],'','',name)
        assert result['subcategory']==expected, (name,result)
        assert result['status']=='suggested'
        assert not {'side','position','fitment','confirmed'} & result.keys()
    assert propose_subcategory(SECTIONS[5],'','','Аеродефлектор')['status']=='review_required'


def test_review_schema_accepts_new_subcategory_without_rewriting_canonical_ids():
    from app.services.universal_catalogue import ReviewedType
    from app.services.canonical_rules import TYPES
    import copy
    before=copy.deepcopy(TYPES)
    r=ReviewedType(source_id=4175,source_sha='0'*64,name_uk='Датчик температури / тиску оливи',
        category=SECTIONS[0],subcategory='Система змащення',kind='review',evidence='Explicit test of proposal validation only')
    assert r.kind=='review'
    assert TYPES==before
