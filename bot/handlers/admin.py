from aiogram import Router, types
from aiogram.filters import Command
from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb

router = Router()


@router.message(Command("start"))
async def start_handler(message: types.Message):
    if message.from_user.id in ADMINS:
        await message.answer("Admin panel", reply_markup=admin_kb)
    else:
        await message.answer("Доступ обмежений")
