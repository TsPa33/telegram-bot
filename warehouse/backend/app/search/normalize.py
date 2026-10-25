"""Predictable transliteration, never applied to stored identifiers or values."""
import re
import unicodedata

CYRILLIC = dict(zip('абвгґдеёжзиіїйклмнопрстуфхцчшщъыьэюя',
    ['a','b','v','g','g','d','e','yo','zh','z','y','i','yi','i','k','l','m','n','o','p','r','s','t','u','f','kh','ts','ch','sh','shch','','y','','e','yu','ya']))
# є is separate so the frozen SQL migration can be parity-tested.
CYRILLIC['є']='ye'
APOSTROPHES="'’ʼ`"

def normalize(value: str) -> str:
    value=unicodedata.normalize('NFKC',value).lower()
    value=re.sub(r'(\d)[.,](\d)',r'\1d\2',value)
    value=''.join(CYRILLIC.get(c,c) for c in value if c not in APOSTROPHES)
    # Decompose Latin accents AFTER Cyrillic transliteration: й must stay distinct.
    value=''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',value))

def identifier(value: str) -> str:
    # Identifier equality ignores separators/case, but NOT Cyrillic/Latin identity.
    return ''.join(c for c in unicodedata.normalize('NFKC',value).lower() if c.isalnum())
