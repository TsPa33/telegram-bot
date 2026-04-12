from bot.database.base import fetchrow, execute, fetch


# ================= SELLER =================

async def get_or_create_seller(telegram_id: int, username: str):
    return await fetchrow("""
        INSERT INTO sellers (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id)
        DO UPDATE SET username = COALESCE(EXCLUDED.username, sellers.username)
        RETURNING *
    """, telegram_id, username)


# ================= CAR =================

async def add_seller_car(seller_id: int, model_id: int, photo_id: str, description: str):
    await execute("""
        INSERT INTO seller_cars (seller_id, model_id, photo_id, description, status)
        VALUES ($1, $2, $3, $4, 'active')
    """, seller_id, model_id, photo_id, description)


async def get_seller_cars(telegram_id: int):
    return await fetch("""
        SELECT sc.id, m.brand, m.model, sc.description
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE s.telegram_id = $1
    """, telegram_id)


# 🔴 FIX: OWNER CHECK
async def delete_car(car_id: int, telegram_id: int):
    await execute("""
        DELETE FROM seller_cars sc
        USING sellers s
        WHERE sc.id = $1
          AND sc.seller_id = s.id
          AND s.telegram_id = $2
    """, car_id, telegram_id)


# 🔴 FIX: OWNER CHECK
async def update_description(car_id: int, description: str, telegram_id: int):
    await execute("""
        UPDATE seller_cars sc
        SET description = $1
        FROM sellers s
        WHERE sc.id = $2
          AND sc.seller_id = s.id
          AND s.telegram_id = $3
    """, description, car_id, telegram_id)


# ================= PROFILE =================

# 🔴 FIX: без f-string

async def update_shop_name(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET shop_name = $1 WHERE id = $2", value, seller_id)


async def update_name(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET name = $1 WHERE id = $2", value, seller_id)


async def update_phone(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET phone = $1 WHERE id = $2", value, seller_id)


async def update_website(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET website = $1 WHERE id = $2", value, seller_id)


async def update_city(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET city = $1 WHERE id = $2", value, seller_id)


async def update_description_profile(seller_id: int, value: str | None):
    await execute("UPDATE sellers SET description = $1 WHERE id = $2", value, seller_id)


FIELD_UPDATE_MAP = {
    "shop_name": update_shop_name,
    "name": update_name,
    "phone": update_phone,
    "website": update_website,
    "city": update_city,
    "description": update_description_profile,
}


async def update_seller_field(seller_id: int, field: str, value: str | None):
    func = FIELD_UPDATE_MAP.get(field)

    if not func:
        return

    await func(seller_id, value)
