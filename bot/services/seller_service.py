from bot.database.repositories.seller_repo import (
    add_seller_car,
    update_description,
    get_or_create_seller
)


async def create_car(
    telegram_id: int,
    username: str,
    model_id: int,
    photo_id: str,
    description: str | None
):
    seller = await get_or_create_seller(telegram_id, username)

    await add_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        photo_id=photo_id,
        description=description
    )


async def edit_car_description(
    car_id: int,
    telegram_id: int,
    description: str | None
) -> bool:
    return await update_description(car_id, description, telegram_id)
