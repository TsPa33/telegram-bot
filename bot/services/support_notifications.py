import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from bot.config import ADMIN_IDS
from bot.database.repositories.crm_admin_repo import list_admin_users

logger = logging.getLogger(__name__)


def admin_display(user) -> str:
    if not user:
        return "адмін"
    if getattr(user, "username", None):
        return f"@{user.username}"
    full_name = getattr(user, "full_name", None)
    return full_name or str(getattr(user, "id", "адмін"))


async def get_support_admin_ids() -> set[int]:
    admin_ids = set(ADMIN_IDS)
    try:
        admin_rows = await list_admin_users()
        admin_ids.update(
            row["telegram_id"]
            for row in admin_rows
            if row.get("is_active") and row.get("role") in {"super_admin", "admin", "manager"}
        )
    except Exception:
        logger.exception("Failed to load support admin recipients")
    return admin_ids


async def notify_support_admins(
    bot: Bot,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    for admin_id in await get_support_admin_ids():
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        except Exception:
            logger.exception("Failed to send support notification to admin %s", admin_id)


async def notify_support_user(bot: Bot, telegram_id: int, text: str) -> None:
    try:
        await bot.send_message(telegram_id, text)
    except Exception:
        logger.exception("Failed to send support notification to user %s", telegram_id)
