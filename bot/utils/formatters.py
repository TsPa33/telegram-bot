import html

def format_car_card(car: dict, page: int, total: int):
    brand = car.get("brand", "")
    model = car.get("model", "")

    description = (car.get("description") or "").strip()
    description = html.escape(description)

    is_catalog = car.get("is_catalog")

    # контакт
    if is_catalog:
        contact = f"📞 {car.get('phone') or 'не вказано'}"
    else:
        if car.get("username"):
            contact = f"@{car['username']}"
        elif car.get("telegram_id"):
            contact = f"<a href='tg://user?id={car['telegram_id']}'>Написати</a>"
        else:
            contact = "⚠️ Контакт відсутній"

    description_block = ""
    if description:
        description_block = f"📝 Опис:\n{description}\n\n"

    return (
        f"<b>{brand} {model}</b>\n\n"
        f"{description_block}"
        f"👤 {contact}\n"
        f"📄 {page + 1} / {total}"
    )
