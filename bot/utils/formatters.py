import html


def safe(val):
    return html.escape(str(val)) if val else ""


def format_car_card(car: dict, page: int | None = None, total: int | None = None):
    brand = safe(car.get("brand"))
    model = safe(car.get("model"))

    title = f"🚗 <b>{brand} {model}</b>"

    # ================= DESCRIPTION =================

    description = safe(car.get("description")) or "Без опису"

    description_block = (
        f"\n📝 <b>Опис:</b>\n{description}\n"
    )

    # ================= SELLER =================

    shop = safe(car.get("shop_name"))
    name = safe(car.get("name"))
    city = safe(car.get("city"))

    seller_lines = []

    if shop:
        seller_lines.append(f"🏪 <b>{shop}</b>")

    if name and name != "🔐 Верифікація":
        seller_lines.append(f"👤 {name}")

    if city:
        seller_lines.append(f"📍 {city}")

    seller_block = ""
    if seller_lines:
        seller_block = "\n\n" + "\n".join(seller_lines)

    # ================= VERIFIED =================

    verified = ""
    if car.get("is_verified"):
        verified = "🔐 <b>Перевірений продавець</b>\n"

    # ================= STATS =================

    views = car.get("views") or 0
    phone = car.get("phone_clicks") or 0
    site = car.get("site_clicks") or 0

    stats_block = (
        "\n\n📊 <b>Статистика</b>\n"
        f"👁 {views}   📞 {phone}   🌐 {site}"
    )

    # ================= PAGINATION =================

    page_block = ""
    if page is not None and total is not None:
        page_block = f"\n\n📄 {page + 1} / {total}"

    # ================= FINAL =================

    return (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{verified}"
        f"{description_block}"
        f"{seller_block}"
        f"{stats_block}"
        f"{page_block}"
    )
