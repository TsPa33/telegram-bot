import html


def safe(val):
    return html.escape(str(val)) if val else ""


def format_car_card(car: dict, page: int | None = None, total: int | None = None):
    # ================= BASIC =================

    brand = safe(car.get("brand"))
    model = safe(car.get("model"))

    title = f"🚗 <b>{brand} {model}</b>"

    # ================= DESCRIPTION =================

    raw_description = car.get("description")

    if raw_description:
        description = safe(str(raw_description).strip())
    else:
        description = "📦 Опис відсутній"

    description_block = (
        "📝 <b>Опис:</b>\n"
        f"{description}\n\n"
    )

    # ================= SELLER =================

    shop_name = safe(car.get("shop_name"))
    name = safe(car.get("name"))
    city = safe(car.get("city"))

    seller_block = ""

    if shop_name:
        seller_block += f"🏪 {shop_name}\n"

    if name:
        seller_block += f"👤 {name}\n"

    if city:
        seller_block += f"📍 {city}\n"

    if seller_block:
        seller_block += "\n"

    # ================= VERIFIED =================

    verified_block = ""
    if car.get("is_verified"):
        verified_block = "🔐 Верифікований продавець\n\n"

    # ================= STATS =================

    views = car.get("views") or 0
    phone_clicks = car.get("phone_clicks") or 0
    site_clicks = car.get("site_clicks") or 0

    stats_block = (
        "📊 <b>Статистика:</b>\n"
        f"👁 Перегляди: {views}\n"
        f"📞 Дзвінки: {phone_clicks}\n"
        f"🌐 Переходи: {site_clicks}"
    )

    # ================= PAGINATION =================

    page_block = ""
    if page is not None and total is not None:
        page_block = f"\n\n📄 {page + 1} / {total}"

    # ================= FINAL =================

    return (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{verified_block}"
        f"{description_block}"
        f"{seller_block}"
        f"{stats_block}"
        f"{page_block}"
    )
