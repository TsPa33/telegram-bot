import pytest
from fastapi import HTTPException
from app.search.normalize import normalize,identifier
from app.search.query import parse,TERMS,DICTIONARY

@pytest.mark.parametrize('q,expected',[
 ('  ФАРА, ліва! ','fara liva'),('радіатор','radiator'),('радиатор','radyator'),
 ('об’єкт',"obyekt"),('2,4 D5','2d4 d5'),('XC60','xc60'),('Škoda Citroën','skoda citroen')])
def test_normalize(q,expected):assert normalize(q)==expected

def test_identifiers_are_not_transliterated_or_rewritten():
    assert identifier('AB-123.45')=='ab12345'
    assert identifier('АВ-123')!='ab123' # Cyrillic is not silently an OEM Latin alias.

def test_protected_constraints_and_ambiguity():
    for q,concept in [('ліва фара','left'),('права фара','right'),('передня фара','front'),('задня фара','rear')]:
        assert any(c==concept and protected for _,_,c,protected in parse(q).groups)
    assert parse('стоп').clarify and parse('ліва права фара').clarify
    assert not parse('задній стоп').clarify and not parse('ліхтар').clarify
    for q in ['x'*161,' '.join(['test']*13)]:
        with pytest.raises(HTTPException):parse(q)

def test_reviewed_dictionary_complexity():
    import re
    from app.search.normalize import normalize
    seen={}
    for term in TERMS.values():
        for form in term['forms']:
            assert seen.setdefault(normalize(form),term['id'])==term['id']
        assert len(term['targets'])<=8
        for phrase in term['targets']:
            assert len(phrase.split(' & '))<=3
            assert all(re.fullmatch(r'=?[a-z0-9]+',t) for t in phrase.split(' & '))
    assert DICTIONARY['version']=='carpot.terms.1'
