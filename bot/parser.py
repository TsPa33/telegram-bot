def parse_input(text: str):
    words = text.lower().split()

    # якщо мало слів — не ламаємось
    if len(words) < 3:
        return None, None, text

    brand = words[-2]
    model = words[-1]
    detail = " ".join(words[:-2])

    return brand, model, detail


# 🔽 ТЕСТ (ПОЗА функцією)
if __name__ == "__main__":
    print(parse_input("тяга рулевая mercedes w203"))
