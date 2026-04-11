import re


# ================= VALIDATION =================

TEXT_PATTERN = re.compile(r"^[A-Za-zА-Яа-яІіЇїЄє0-9\s\-]{2,50}$")


def validate_text(text: str) -> bool:
    if not text:
        return False

    text = text.strip()

    if len(text) < 2 or len(text) > 50:
        return False

    return bool(TEXT_PATTERN.match(text))


# ================= NORMALIZATION =================

def normalize_brand(text: str) -> str:
    """
    Нормалізація бренду:
    - прибирає пробіли
    - робить першу літеру великою, інші як є
    """
    text = text.strip()

    if not text:
        return text

    return text[0].upper() + text[1:].lower()


def normalize_model(text: str) -> str:
    """
    Нормалізація моделі:
    - зберігає регістр цифр
    - робить першу літеру великою
    """
    text = text.strip()

    if not text:
        return text

    return text[0].upper() + text[1:]
