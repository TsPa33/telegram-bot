import uuid

from aiogram import Router, F
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.payment_repo import create_payment
from bot.services.liqpay_service import LiqPayService
from bot.config import LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY, LIQPAY_CALLBACK_URL

router = Router()

liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


@router.message(F.text == "💳 Купити 1 слот — 99 грн")
async def buy_slot(message: Message):
    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

    order_id = str(uuid.uuid4())
    amount = 99

    await create_payment(seller["id"], order_id, amount)

    url = liqpay.generate_checkout_url(
        order_id=order_id,
        amount=amount,
        description="Buy 1 car slot",
        server_url=LIQPAY_CALLBACK_URL
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатити", url=url)

    await message.answer("💳 Оплата:", reply_markup=kb.as_markup())
