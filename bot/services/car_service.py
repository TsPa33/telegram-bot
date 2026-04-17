from bot.database.repositories.model_repo import get_model_id
from bot.database.repositories.car_repo import get_cars_page as repo_get_cars_page
from bot.database.repositories.car_repo import count_cars


# ================= MODEL =================

async def get_model_or_none(brand: str, model: str) -> int | None:
    return await get_model_id(brand, model)


# ================= PAGINATION =================

async def get_cars_page(model_id: int, page: int, limit: int = 1):
    """
    Узгоджено з repo
    """

    total_items = await count_cars(model_id)

    if total_items == 0:
        return None, 0

    total_pages = total_items  # бо LIMIT = 1

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1)

    cars = await repo_get_cars_page(
        model_id=model_id,
        limit=limit,
        offset=offset
    )

    car = cars[0] if cars else None

    return car, total_pages
