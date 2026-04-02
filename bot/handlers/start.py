from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from bot.keyboards.role import role_keyboard

router = Router()

# тимчасове сховище (поки без БД)
users = {}


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Обери хто ти:",
        reply_markup=role_keyboard()
    )


@router.callback_query()
async def handle_role(callback: CallbackQuery):
    user_id = callback.from_user.id

    if callback.data == "role_seller":
        users[user_id] = "seller"
        await callback.message.answer("Ти обрав: Продавець")

    elif callback.data == "role_buyer":
        users[user_id] = "buyer"
        await callback.message.answer("Ти обрав: Покупець")

    await callback.answer()
