import html


def format_car_card(car: dict, page: int, total: int):
    # ================= BASIC =================

    brand = html.escape(car.get("brand") or "")
    model = html.escape(car.get("model") or "")

    title = f"🚗 <b>{brand} {model}</b>"

    # ================= DESCRIPTION (FIXED) =================

    raw_description = car.get("description")

    if raw_description is None:
        description = ""
    else:
        description = str(raw_description).strip()

    description = html.escape(description)

    # 🔴 FIX: fallback
    if not description:
        description = "📦 Опис відсутній"

    description_block = (
        "📝 <b>Опис:</b>\n"
        f"{description}\n\n"
    )

    # ================= SELLER =================

    shop_name = html.escape(car.get("shop_name") or "")
    name = html.escape(car.get("name") or "")
    city = html.escape(car.get("city") or "")

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

    verified = car.get("is_verified")

    if verified:
        verified_block = "✅ Перевірений продавець\n\n"
    else:
        verified_block = "⚠️ Продавець не перевірений\n\n"

    # ================= PAGINATION =================

    page_block = f"📄 {page + 1} / {total}"

    # ================= FINAL =================

    return (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{verified_block}"
        f"{description_block}"
        f"{seller_block}"
        f"{page_block}"
    )
