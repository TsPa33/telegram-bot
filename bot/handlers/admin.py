from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb
from bot.states.admin_states import AddUser

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
  @router.message(AddUser.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введіть посилання на сайт:")
    await state.set_state(AddUser.website)  
    @router.message(AddUser.website)
async def get_website(message: types.Message, state: FSMContext):
    await state.update_data(website=message.text)
    await message.answer("Введіть номер телефону:")
    await state.set_state(AddUser.phone)
@router.message(AddUser.phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Введіть бренди (кожен з нового рядка):")
    await state.set_state(AddUser.brands)
    @router.message(AddUser.brands)
async def get_brands(message: types.Message, state: FSMContext):
    brands = [b.strip() for b in message.text.split("\n") if b.strip()]

    await state.update_data(brands=brands)
    await message.answer("Введіть моделі (кожна з нового рядка):")
    await state.set_state(AddUser.models)
    from bot.database.db import add_user

@router.message(AddUser.models)
async def get_models(message: types.Message, state: FSMContext):
    models = [m.strip() for m in message.text.split("\n") if m.strip()]

    data = await state.update_data(models=models)

    add_user(data)

    await message.answer("✅ Користувача додано")
    await state.clear()
