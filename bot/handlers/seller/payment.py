from aiogram import Router, F
from aiogram.types import CallbackQuery
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


@router.callback_query(F.data == "buy_slot")
async def buy_slot(callback: CallbackQuery):
    try:
        await callback.answer()  # ✅ обовʼязково

        # 🔹 продавець
        seller = await get_or_create_seller(
            callback.from_user.id,
            callback.from_user.username
        )

        # 🔹 платіж
        payment = await liqpay.create_payment(
            amount=99,
            description="Buy 1 car slot",
            server_url=LIQPAY_CALLBACK_URL
        )

        url = payment["url"]

        # 🔹 кнопка
        kb = InlineKeyboardBuilder()
        kb.button(text="Оплатити", url=url)

        await callback.message.answer(
            "💳 Оплата:",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print("ERROR BUY SLOT:", e)
        await callback.message.answer("⚠️ Сталась помилка")
