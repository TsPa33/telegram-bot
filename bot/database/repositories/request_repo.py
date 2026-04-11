from bot.database.base import execute, fetch


# ================= MODEL REQUEST =================

async def add_model_request(user_id: int, brand: str, model: str):
    await execute("""
        INSERT INTO model_requests (user_id, brand, model)
        VALUES ($1, $2, $3)
    """, user_id, brand, model)


# ================= BRAND REQUEST =================

async def add_brand_request(user_id: int, brand: str):
    await execute("""
        INSERT INTO brand_requests (user_id, brand)
        VALUES ($1, $2)
    """, user_id, brand)
