from bot.database.repositories.car_repo import find_cars, count_cars
from bot.database.repositories.model_repo import get_model_id


# ================= MODEL =================

async def get_model_or_none(brand: str, model: str):
    return await get_model_id(brand, model)


# ================= CARS =================

async def get_cars_page(model_id: int, page: int):
    total = await count_cars(model_id)

    if total == 0:
        return None, 0

    # 🔴 LIMIT = 1 → OFFSET = page
    cars = await find_cars(model_id, page, limit=1)

    if not cars:
        return None, total

    car = cars[0]

    # 🔴 FIX: нормалізація description
    if car.get("description") is None:
        car["description"] = ""

    return car, total
