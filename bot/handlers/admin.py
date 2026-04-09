from aiogram import Router, types
from aiogram.filters import Command
from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb
from bot.states.admin_states import AddUser
from aiogram.fsm.context import FSMContext

router = Router()


@router.message(Command("start"))
async def start_handler(message: types.Message):
    if message.from_user.id in ADMINS:
        await message.answer("Admin panel", reply_markup=admin_kb)
    else:
        await message.answer("Доступ обмежений")
        @router.message(lambda m: m.text == "➕ Додати користувача")
async def add_user_start(message: types.Message, state: FSMContext):
    await message.answer("Введіть ім'я користувача:")
    await state.set_state(AddUser.name)
