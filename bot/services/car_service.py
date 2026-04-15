from bot.database.repositories.car_repo import find_cars, count_cars
from bot.database.repositories.model_repo import get_model_id


# ================= FIND FLOW =================

async def get_model_or_none(brand: str, model: str):
    return await get_model_id(brand, model)


async def get_cars_page(model_id: int, page: int):
    total = await count_cars(model_id)

    if total == 0:
        return None, 0

    cars = await find_cars(model_id, page, limit=1)

    if not cars:
        return None, total

    return cars[0], total
