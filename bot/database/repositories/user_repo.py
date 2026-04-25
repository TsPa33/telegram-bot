from bot.database.base import execute, fetch


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
