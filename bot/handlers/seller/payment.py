from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.repositories.seller_repo import get_or_create_seller
from bot.services.liqpay_service import LiqPayService
from bot.config import (
    LIQPAY_PUBLIC_KEY,
    LIQPAY_PRIVATE_KEY,
    LIQPAY_CALLBACK_URL
)

router = Router()

liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


@router.message(F.text == "💳 Купити 1 слот — 99 грн")
async def buy_slot(message: Message):
    try:
        # 🔹 1. отримуємо продавця
        seller = await get_or_create_seller(
            message.from_user.id,
            message.from_user.username
        )

        # 🔹 2. створюємо платіж (БЕЗ conn!)
        payment = await liqpay.create_payment(
            amount=99,
            description="Buy 1 car slot",
            server_url=LIQPAY_CALLBACK_URL
        )

        url = payment["url"]

        # 🔹 3. кнопка оплати
        kb = InlineKeyboardBuilder()
        kb.button(text="Оплатити", url=url)

        await message.answer(
            "💳 Оплата:",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print("ERROR BUY SLOT:", e)
        await message.answer("⚠️ Сталась помилка")
