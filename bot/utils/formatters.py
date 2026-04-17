import html


def safe(val):
    return html.escape(str(val)) if val else ""


def format_car_card(car: dict, page: int | None = None, total: int | None = None):
    brand = safe(car.get("brand"))
    model = safe(car.get("model"))

    title = f"🚗 <b>{brand} {model}</b>"

    # ================= DESCRIPTION =================

    description = safe(car.get("description")) or "Без опису"

    description_block = f"\n{description}\n"

    # ================= SELLER =================

    shop = safe(car.get("shop_name"))
    name = safe(car.get("name"))
    city = safe(car.get("city"))

    seller_parts = []

    if shop:
        seller_parts.append(f"🏪 {shop}")

    if name and name != "🔐 Верифікація":
        seller_parts.append(f"👤 {name}")

    if city:
        seller_parts.append(f"📍 {city}")

    seller_block = ""
    if seller_parts:
        seller_block = "\n" + " | ".join(seller_parts)

    # ================= VERIFIED =================

    verified = ""
    if car.get("is_verified"):
        verified = "🔐 Перевірений продавець\n"

    # ================= STATS =================

    views = car.get("views") or 0
    phone = car.get("phone_clicks") or 0
    site = car.get("site_clicks") or 0

    stats_block = f"\n📊 👁 {views}   📞 {phone}   🌐 {site}"

    # ================= PAGINATION =================

    page_block = ""
    if page is not None and total is not None:
        page_block = f"\n\n⬅️ {page}/{total} ➡️"

    # ================= FINAL =================

    return (
        f"{title}\n"
        f"{verified}"
        f"{description_block}"
        f"{seller_block}"
        f"{stats_block}"
        f"{page_block}"
    )
