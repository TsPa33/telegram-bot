"""Conservative linguistic quality gate for new *catalogue* names at import preview.
This does not translate names or infer fitment, and does not affect existing IDs.
Names with a strong Russian-language signal require explicit admin resolution.
"""
import re

_RUSSIAN_LETTERS = re.compile(r"[ыъёэЫЪЁЭ]")
_RUSSIAN_WORDS = re.compile(
    r"(?<!\w)(?:двигатель|подвеска|передний|передняя|задний|задняя|"
    r"левый|левая|правый|правая|главная|передача|тормозной|тормозная|рулевое|"
    r"стекло|стеклоподъемник|охлаждение|освещение|оборудование|"
    r"крыло|дверь|двери|сцепления|привод|ременный|"
    r"внутренняя|отделка|безопасность|колеса|колёса|шины|"
    r"топливная|жидкости|система выпуска|система зажигания)\b",
    re.IGNORECASE,
)

def needs_ukrainian_review(name: str) -> bool:
    """Flag strong Russian signals; do not rewrite unknown automotive terms."""
    value = str(name or "").strip()
    return bool(_RUSSIAN_LETTERS.search(value) or _RUSSIAN_WORDS.search(value))
