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


# ✅ ПІДТРИМКА НОВОЇ І СТАРОЇ КНОПКИ
@router.message(F.text.in_(["💳 Купити 1 слот — 99 грн", "💳 Пакети послуг"]))
async def buy_slot(message: Message):
    try:
        # 🔹 продавець
        seller = await get_or_create_seller(
            message.from_user.id,
            message.from_user.username
        )

        # 🔹 платіж
        payment = await liqpay.create_payment(
            amount=99,
            description="Buy 1 car slot",
            server_url=LIQPAY_CALLBACK_URL,
            seller_id=seller["id"]
        )

        url = payment["url"]

        # 🔹 кнопка оплати
        kb = InlineKeyboardBuilder()
        kb.button(text="Оплатити", url=url)

        await message.answer(
            "💳 Оплата:\n\n"
            "🔹 1 слот — 99 грн\n\n"
            "Натисни кнопку нижче для оплати:",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print("ERROR BUY SLOT:", e)
        await message.answer("⚠️ Сталась помилка")
