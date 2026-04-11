import re

TEXT_PATTERN = re.compile(r"^[A-Za-zА-Яа-яІіЇїЄє0-9\s\-]{2,50}$")


def validate_text(text: str) -> bool:
    if not text:
        return False

    text = text.strip()

    if len(text) < 2 or len(text) > 50:
        return False

    return bool(TEXT_PATTERN.match(text))


def normalize_brand(text: str) -> str:
    return text.strip().upper()


def normalize_model(text: str) -> str:
    return text.strip()
