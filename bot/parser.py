from urllib.parse import quote


# ================= INPUT =================

def parse_input(text: str):
    words = text.lower().split()

    if len(words) < 3:
        return None, None, text

    brand = words[-2]
    model = words[-1]
    detail = " ".join(words[:-2])

    return brand, model, detail


# ================= URL =================

def build_url(brand, model, detail):
    query = f"{detail} {brand} {model}"
    return f"https://podkapot.com.ua/search?query={quote(query)}"


# ================= TEST =================

if __name__ == "__main__":
    print(parse_input("тяга рулевая mercedes w203"))
    print(build_url("mercedes", "w203", "тяга рулевая"))
