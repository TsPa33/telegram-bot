def format_car_card(car: dict, page: int, total: int) -> str:
    description = car.get("description") or "📦 Опис відсутній"

    shop_name = car.get("shop_name") or "Без назви"
    name = car.get("name") or "Не вказано"
    phone = car.get("phone") or "не вказано"
    website = car.get("website") or "-"
    city = car.get("city") or "-"

    seller_block = (
        f"🏪 <b>{shop_name}</b>\n"
        f"👤 {name}\n"
        f"📞 {phone}\n"
        f"🌐 {website}\n"
        f"📍 {city}"
    )

    text = (
        f"🚗 <b>{car['brand']} {car['model']}</b>\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📝 <b>Опис:</b>\n{description}\n\n"
        f"{seller_block}\n\n"
        f"📄 <b>{page + 1} / {total}</b>"
    )

    return text
