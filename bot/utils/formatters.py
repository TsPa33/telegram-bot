def format_car_card(
    brand: str,
    model: str,
    description: str | None,
    username: str | None,
    page: int,
    total: int
) -> str:
    description = description or "📦 Опис відсутній"

    seller_block = (
        f"👤 <b>Продавець:</b> @{username}"
        if username
        else "👤 <b>Продавець:</b> не вказано"
    )

    return (
        f"🚗 <b>{brand} {model}</b>\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📝 <b>Опис:</b>\n"
        f"{description}\n\n"
        f"{seller_block}\n\n"
        f"📄 <b>Оголошення:</b> {page + 1} / {total}"
    )
