import logging

from aiogram import Bot

from bot.config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
logger = logging.getLogger(__name__)


async def _send_message(telegram_id: int, text: str, *, audience: str, reply_markup=None, parse_mode: str | None = None):
    try:
        return await bot.send_message(
            chat_id=telegram_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception as exc:
        logger.warning(
            "Unable to send Telegram message audience=%s telegram_id=%s: %s",
            audience,
            telegram_id,
            exc,
        )
        return None


async def send_message_to_seller(telegram_id: int, text: str, *, reply_markup=None, parse_mode: str | None = None):
    return await _send_message(
        telegram_id,
        text,
        audience="seller",
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


async def send_message_to_buyer(telegram_id: int, text: str, *, reply_markup=None, parse_mode: str | None = None):
    return await _send_message(
        telegram_id,
        text,
        audience="buyer",
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )
