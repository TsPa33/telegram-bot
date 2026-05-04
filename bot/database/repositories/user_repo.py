from bot.database.base import execute, fetch, fetchrow


# ================= VISITS =================

async def log_visit(user, role: str, phone: str | None = None):
    await execute("""
        INSERT INTO user_visits (telegram_id, name, username, phone, role)
        VALUES ($1, $2, $3, $4, $5)
    """,
    user.id,
    user.first_name,
    user.username,
    phone,
    role
    )


async def get_visits():
    return await fetch("""
        SELECT 
            DATE(created_at) as date,
            telegram_id,
            name,
            username,
            phone,
            role
        FROM user_visits
        ORDER BY created_at DESC
    """)


# ================= USERS =================

async def create_user(telegram_id: int, username: str | None):
    """
    Створює користувача якщо його ще немає
    """
    return await execute("""
        INSERT INTO users (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO NOTHING
    """, telegram_id, username)


async def get_all_users(limit: int = 20):
    return await fetch("""
        SELECT id, telegram_id, username
        FROM users
        ORDER BY id DESC
        LIMIT $1
    """, limit)


async def get_user_by_id(user_id: int):
    return await fetchrow("""
        SELECT *
        FROM users
        WHERE id = $1
        LIMIT 1
    """, user_id)


async def delete_user(user_id: int):
    return await execute("""
        DELETE FROM users
        WHERE id = $1
    """, user_id)


# ================= SAFE DELETE (FIXED) =================

async def delete_user_full(user_id: int):
    try:
        # 🔍 отримуємо telegram_id
        user = await fetchrow("""
            SELECT telegram_id FROM users WHERE id = $1
        """, user_id)

        if not user:
            print("❌ USER NOT FOUND:", user_id)
            return

        telegram_id = user["telegram_id"]

        # 🔥 seller
        seller = await fetchrow("""
            SELECT id FROM sellers WHERE user_id = $1
        """, user_id)

        if seller:
            seller_id = seller["id"]

            await execute("DELETE FROM seller_sites WHERE seller_id = $1", seller_id)
            await execute("DELETE FROM services WHERE seller_id = $1", seller_id)
            await execute("DELETE FROM cars WHERE seller_id = $1", seller_id)
            await execute("DELETE FROM sellers WHERE id = $1", seller_id)

        # 🔥 visits
        if telegram_id:
            await execute("""
                DELETE FROM user_visits 
                WHERE telegram_id = $1
            """, telegram_id)

        # 🔥 user
        result = await execute("""
            DELETE FROM users WHERE id = $1
        """, user_id)

        print("✅ DELETE RESULT:", result)

    except Exception as e:
        print("❌ DELETE ERROR:", e)
