# ================= MODELS PARSER =================

def clean_line(line: str) -> str:
    return line.strip().lower()


def extract_brand_and_model(line: str):
    words = line.split()

    if not words:
        return None, None

    # бренд
    brand = words[0]

    # якщо тільки бренд
    if len(words) == 1:
        return brand, None

    # модель = все інше
    model = " ".join(words[1:])

    # 🔥 чистка
    garbage = [
        "(", ")", "restyling", "lci", "sportback"
    ]

    # прибираємо дужки і текст після них
    if "(" in model:
        model = model.split("(")[0]

    # прибираємо роки
    for year in ["202", "201", "200", "199"]:
        if year in model:
            model = model.split(year)[0]

    # прибираємо сміття
    for g in garbage:
        model = model.replace(g, "")

    return brand, model.strip()


def parse_models(text: str):
    brands = set()
    models = set()

    lines = text.split("\n")

    for line in lines:
        line = clean_line(line)

        if not line:
            continue

        # службові рядки
        if "марка авто" in line or "модель авто" in line:
            continue

        # ігноруємо опис
        if "всі моделі" in line:
            continue

        brand, model = extract_brand_and_model(line)

        if brand:
            brands.add(brand)

        if model:
            models.add(model)

    return {
        "brands": list(brands),
        "models": list(models)
    }


# ================= DATABASE BUILDER =================

def build_seller(row):
    parsed = parse_models(row[6] if len(row) > 6 else "")

    return {
        "name": row[0],
        "site": row[1],
        "phone": row[2],
        "brands": parsed["brands"],
        "models": parsed["models"]
    }


def build_database(data):
    sellers = []

    for row in data:
        if len(row) < 3:
            continue

        seller = build_seller(row)
        sellers.append(seller)

    return sellers


# ================= SEARCH =================

def normalize(text: str) -> str:
    return text.lower().replace("-", "").strip()


def find_sellers_by_model(sellers, brand: str, model: str):
    brand = normalize(brand)
    model = normalize(model)

    results = []

    for seller in sellers:
        seller_brands = [normalize(b) for b in seller["brands"]]
        seller_models = [normalize(m) for m in seller["models"]]

        if brand in seller_brands and model in seller_models:
            results.append(seller)

    return results[:5]


# ================= TEST =================

if __name__ == "__main__":

    # тестові дані
    RAW_DATA = [
        [
            "Tesla Склад",
            "https://tesla-sklad.com.ua/",
            "38(098)333-18-43",
            "",
            "",
            "",
            """Всі моделі Tesla
Model 3 2016-2023
Model S Plaid
Model X 2016-2018"""
        ],
        [
            "Autodonor",
            "https://leafparts.in.ua/",
            "38(095)672-67-67",
            "",
            "",
            "",
            """Ford F-150
Tesla Model 3"""
        ]
    ]

    db = build_database(RAW_DATA)

    print("\nDATABASE:")
    for s in db:
        print(s)

    print("\nSEARCH TEST:")
    result = find_sellers_by_model(db, "tesla", "model 3")

    for r in result:
        print(r)
