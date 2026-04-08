def parse_input(text: str):
    words = text.lower().split()

    # якщо мало слів — не ламаємося
    if len(words) < 3:
        return None, None, text

    brand = words[-2]
    model = words[-1]
    detail = " ".join(words[:-2])

    return brand, model, detail
