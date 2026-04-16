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

    # ================= VERIFIED (тимчасово вимкнено) =================

    verified_block = ""  # 🔥 щоб не падало (поки немає поля в БД)

   # ================= STATS =================

views = car.get("views") or 0
phone_clicks = car.get("phone_clicks") or 0
site_clicks = car.get("site_clicks") or 0

stats_block = (
    f"📊 Статистика:\n"
    f"👁 Перегляди: {views}\n"
    f"📞 Дзвінки: {phone_clicks}\n"
    f"🌐 Переходи: {site_clicks}"
)

# ================= CARD =================

text = (
    f"🚗 <b>{car['brand']} {car['model']}</b>\n"
    f"{'─' * 20}\n\n"

    f"📝 Опис:\n{car.get('description') or '-'}\n\n"

    f"🏪 {car.get('shop_name') or '-'}\n"
    f"👤 {'🔐 Верифікований' if car.get('is_verified') else '❌ Не верифікований'}\n"
    f"📍 {car.get('city') or '-'}\n\n"

    f"{stats_block}"
)

    # ================= PAGINATION =================

    if page is not None and total is not None:
        page_block = f"📄 {page + 1} / {total}"
    else:
        page_block = ""

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
