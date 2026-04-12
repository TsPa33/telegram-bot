async def parse_seller_file(text: str):
    rows = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]

        if len(parts) != 6:
            continue

        shop_name, website, phone, name, brand, model = parts

        rows.append({
            "shop_name": shop_name,
            "website": website,
            "phone": phone,
            "name": name,
            "brand": brand,
            "model": model
        })

    return rows
