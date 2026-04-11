import re


def validate_text(text: str):
    if not text:
        return False
    return bool(re.match(r"^[A-Za-z0-9\s\-]{2,50}$", text.strip()))


def normalize_brand(text: str) -> str:
    return text.strip().title()


def normalize_model(text: str) -> str:
    return text.strip().upper()
