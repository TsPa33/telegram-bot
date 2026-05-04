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


# ================= SAFE DELETE (RECOMMENDED) =================

async def delete_user_full(user_id: int):
    """
    Безпечне видалення:
    видаляє все що пов'язано з користувачем
    """

    # отримати seller
    seller = await fetchrow("""
        SELECT id FROM sellers WHERE user_id = $1
    """, user_id)

    if seller:
        seller_id = seller["id"]

        # site
        await execute("DELETE FROM seller_sites WHERE seller_id = $1", seller_id)

        # services
        await execute("DELETE FROM services WHERE seller_id = $1", seller_id)

        # cars (якщо є таблиця)
        await execute("DELETE FROM cars WHERE seller_id = $1", seller_id)

        # seller
        await execute("DELETE FROM sellers WHERE id = $1", seller_id)

    # visits
    await execute("DELETE FROM user_visits WHERE telegram_id IN (SELECT telegram_id FROM users WHERE id = $1)", user_id)

    # user
    await execute("DELETE FROM users WHERE id = $1", user_id)
