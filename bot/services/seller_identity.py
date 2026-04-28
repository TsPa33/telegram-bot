from aiogram.types import Message, User

from bot.database.repositories.seller_repo import get_or_create_seller


# ================= CORE =================

async def resolve_seller(message: Message) -> dict:
    """
    Завжди повертає валідного seller
    """
    user = message.from_user

    return await get_or_create_seller(
        telegram_id=user.id,
        username=user.username
    )


async def resolve_seller_from_user(user: User) -> dict:
    """
    Для callback / інших випадків
    """
    return await get_or_create_seller(
        telegram_id=user.id,
        username=user.username
    )
