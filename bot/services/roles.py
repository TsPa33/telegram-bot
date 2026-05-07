from bot.config import ADMIN_IDS
from bot.database.base import fetch


async def is_seller(user_id: int) -> bool:
    row = await fetch(
        "SELECT id FROM sellers WHERE telegram_id = $1 LIMIT 1",
        user_id,
    )
    return bool(row)


async def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True

    row = await fetch(
        """
        SELECT id
        FROM admin_users
        WHERE telegram_id = $1
          AND is_active = TRUE
          AND role IN ('super_admin', 'admin')
        LIMIT 1
        """,
        user_id,
    )

    return bool(row)
