from bot.config import ADMIN_IDS
from bot.database.base import fetch

CRM_SUPER_ADMIN_ID = 7553546170


async def is_seller(user_id: int) -> bool:
    row = await fetch(
        "SELECT id FROM sellers WHERE telegram_id = $1 LIMIT 1",
        user_id,
    )
    return bool(row)


async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or user_id == CRM_SUPER_ADMIN_ID
