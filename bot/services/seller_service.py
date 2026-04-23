from bot.database.repositories.seller_repo import (
    add_seller_car,
    update_description,
    get_or_create_seller,
    update_seller_logo
)
from bot.database.base import execute
from bot.services.logo_service import get_logo


# ================= CREATE CAR =================

async def create_car(
    telegram_id: int,
    username: str,
    model_id: int,
    photo_id: str,
    description: str | None
):
    # 🔥 ВАЖЛИВО: беремо об'єкт, а не id
    seller = await get_or_create_seller(telegram_id, username)

    await add_seller_car(
        seller_id=seller["id"],   # ✅ правильний id
        model_id=model_id,
        photo_id=photo_id,
        description=description
    )


# ================= EDIT DESCRIPTION =================

async def edit_car_description(
    car_id: int,
    telegram_id: int,
    description: str | None
) -> bool:
    return await update_description(car_id, description, telegram_id)


# ================= WEBSITE + LOGO =================

async def set_seller_website_and_logo(
    telegram_id: int,
    website_url: str
):
    # отримуємо seller
    seller = await get_or_create_seller(telegram_id, username=None)

    # 1. зберігаємо website
    await execute("""
        UPDATE sellers
        SET website = $1
        WHERE id = $2
    """, website_url, seller["id"])

    # 2. парсимо logo
    logo_url = await get_logo(website_url)

    # 3. зберігаємо logo
    await update_seller_logo(seller["id"], logo_url)

    return logo_url
