def validate_text(text: str):
    return text and text.strip()


def normalize(text: str):
    return text.lower().strip().capitalize()
