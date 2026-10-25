"""A bounded query plan; dictionaries describe retrieval, never vehicle fitment."""
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from fastapi import HTTPException
from .normalize import normalize, identifier

DICTIONARY=json.loads(Path(__file__).with_name('terms.json').read_text())
TERMS={t['id']:t for t in DICTIONARY['terms']}
FORMS={normalize(form):t['id'] for t in TERMS.values() for form in t['forms']}
BRANDS={normalize(form):key for key,forms in DICTIONARY['brands'].items() for form in [key,*forms]}
MODELS={normalize(form):key for key,forms in DICTIONARY['models'].items() for form in [key,*forms]}
STOP={normalize(t) for t in DICTIONARY['stopwords']}
PAIRS={'left':'right','right':'left','front':'rear','rear':'front','auto':'manual','manual':'auto','diesel':'petrol','petrol':'diesel'}

def ts_group(targets):
    # Only reviewed dictionary targets or normalized [a-z0-9] tokens reach tsquery.
    return '('+' | '.join('('+' & '.join(word[1:] if word.startswith('=') else word+(':*' if len(word)>2 else '') for word in phrase.split(' & '))+')' for phrase in targets)+')'

@dataclass
class Plan:
    raw: str
    tokens: list[str]
    groups: list[tuple[str,str,str,bool]]=field(default_factory=list) # token, tsquery, concept, protected
    brands: list[str]=field(default_factory=list)
    models: list[str]=field(default_factory=list)
    generations: list[str]=field(default_factory=list)
    years: list[int]=field(default_factory=list)
    codes: list[str]=field(default_factory=list)
    clarify: str=''


def parse(q: str, discovered: dict[str,set[str]] | None=None) -> Plan:
    text=normalize(q);raw_tokens=text.split();tokens=list(dict.fromkeys(raw_tokens))
    if len(q)>160 or len(raw_tokens)>12:raise HTTPException(422,'До 160 символів і 12 слів у запиті')
    result=Plan(q,tokens);discovered=discovered or {}
    if q.strip() and (not tokens or all(len(t)<2 for t in tokens)):
        result.clarify='Введіть щонайменше два символи або точний OEM.';return result
    has_car=any(t in BRANDS or t in MODELS or 'brand' in discovered.get(t,set()) or 'model' in discovered.get(t,set()) for t in tokens)
    for token in tokens:
        roles=discovered.get(token,set())
        if token in BRANDS:result.brands.append(BRANDS[token]);continue
        if 'brand' in roles:result.brands.append(token);continue
        if token in MODELS:result.models.append(MODELS[token]);continue
        if 'model' in roles:result.models.append(token);continue
        if has_car and ('generation' in roles or token in {'i','ii','iii','iv','v','vi'}):result.generations.append(token);continue
        if len(tokens)>1 and re.fullmatch(r'(19|20)\d\d',token):result.years.append(int(token));continue
        if token in STOP:continue
        concept=FORMS.get(token,'');entry=TERMS.get(concept)
        protected=bool(entry and entry.get('protected')) or (len(tokens)>1 and bool(re.fullmatch(r'\d+d\d+',token)))
        result.groups.append((token,ts_group(entry['targets']) if entry else '('+token+(':*' if len(token)>=2 and not protected else '')+')',concept,protected))
    concepts={g[2] for g in result.groups}
    for concept in sorted(concepts):
        implied=TERMS.get(concept,{}).get('implies')
        if implied and implied not in concepts:
            entry=TERMS[implied]
            result.groups.append((normalize(entry['forms'][0]),ts_group(entry['targets']),implied,bool(entry.get('protected'))))
            concepts.add(implied)
    if len(result.groups)>8:raise HTTPException(422,'Уточніть запит: до 8 пошукових понять')
    if any(a in concepts and b in concepts for a,b in PAIRS.items()):
        result.clarify='Уточніть сторону, розташування або тип двигуна/коробки: запит містить суперечливі обмеження.'
    for token,_,concept,_ in result.groups:
        requirement=TERMS.get(concept,{}).get('requires')
        if requirement and token in {normalize(x) for x in TERMS[concept].get('ambiguous_forms',[])} and requirement not in concepts:
            result.clarify='Уточніть «стоп»: задній ліхтар чи інша деталь? Додайте розташування або технічну назву.'
    # OEM/article rules stay separate from transliteration. Full query first;
    # mixed queries can include identifier-like atoms after donor extraction.
    result.codes=[identifier(q)] if identifier(q) else []
    car_tokens=set(result.brands+result.models+result.generations)
    for atom in q.split():
        clean=identifier(atom);normalized=normalize(atom)
        if re.search(r'\d',clean) and normalized not in car_tokens and normalized not in MODELS and not (len(tokens)>1 and re.fullmatch(r'(19|20)\d\d',normalized)):
            result.codes.append(clean)
    result.codes=list(dict.fromkeys(result.codes))[:4]
    return result


def surface(raw: str, token: str) -> str:
    """Quote what the user typed, not the internal transliteration."""
    for atom in re.findall(r"[^\W_]+(?:[’'ʼ`][^\W_]+)*",raw):
        if normalize(atom)==token:return atom
    return token
