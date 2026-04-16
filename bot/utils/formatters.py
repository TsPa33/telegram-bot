import html


def format_car_card(car: dict, page: int | None = None, total: int | None = None):
    brand = html.escape(str(car.get("brand") or ""))
    model = html.escape(str(car.get("model") or ""))

    title = f"🚗 <b>{brand} {model}</b>"

    raw_description = car.get("description")
    description = html.escape(str(raw_description).strip()) if raw_description else ""

    if not description:
        description = "📦 Опис відсутній"

    description_block = (
        "📝 <b>Опис:</b>\n"
        f"{description}\n\n"
    )

    shop_name = html.escape(str(car.get("shop_name") or ""))
    name = html.escape(str(car.get("name") or ""))
    city = html.escape(str(car.get("city") or ""))

    seller_block = ""

    if shop_name:
        seller_block += f"🏪 {shop_name}\n"

    if name:
        seller_block += f"👤 {name}\n"

    if city:
        seller_block += f"📍 {city}\n"

    if seller_block:
        seller_block += "\n"

    verified = car.get("is_verified")
    verified_block = "✅ Перевірений продавець\n\n" if verified else "⚠️ Продавець не перевірений\n\n"

    views = car.get("views") or 0
    phone_clicks = car.get("phone_clicks") or 0
    site_clicks = car.get("site_clicks") or 0

    stats_block = (
        f"👁 Перегляди: {views}\n"
        f"📞 Дзвінки: {phone_clicks}\n"
        f"🌐 Переходи: {site_clicks}\n\n"
    )

    # 🔥 FIX
    if page is not None and total is not None:
        page_block = f"📄 {page + 1} / {total}"
    else:
        page_block = ""

    return (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{verified_block}"
        f"{description_block}"
        f"{seller_block}"
        f"{stats_block}"
        f"{page_block}"
    )
