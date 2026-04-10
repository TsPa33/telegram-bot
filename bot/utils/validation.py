def validate_text(text: str):
    return text and text.strip()


def normalize(text: str) -> str:
    return text.strip().upper()
