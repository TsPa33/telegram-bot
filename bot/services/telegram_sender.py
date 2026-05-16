import logging

from aiogram import Bot

from bot.config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
logger = logging.getLogger(__name__)


async def send_message_to_seller(telegram_id: int, text: str, *, reply_markup=None, parse_mode: str | None = None):
    try:
        return await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception as exc:
        logger.warning("Unable to send Telegram message to seller telegram_id=%s: %s", telegram_id, exc)
        return None
