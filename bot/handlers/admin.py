from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb
from bot.states.admin_states import AddUser
from bot.database.db import add_user

router = Router()



@router.message(lambda m: m.text == "➕ Додати користувача")
async def add_user_start(message: types.Message, state: FSMContext):
    await message.answer("Введіть ім'я користувача:")
    await state.set_state(AddUser.name)


# 1️⃣ ІМ'Я → САЙТ
@router.message(AddUser.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введіть посилання на сайт:")
    await state.set_state(AddUser.website)


# 2️⃣ САЙТ → ТЕЛЕФОН
@router.message(AddUser.website)
async def get_website(message: types.Message, state: FSMContext):
    await state.update_data(website=message.text)
    await message.answer("Введіть номер телефону:")
    await state.set_state(AddUser.phone)


# 3️⃣ ТЕЛЕФОН → МОДЕЛІ
@router.message(AddUser.phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)

    await message.answer(
        "Введіть моделі у форматі:\n\n"
        "Model: Audi\n"
        "A4\n"
        "A6\n\n"
        "Model: BMW\n"
        "E60\n"
        "F30\n\n"
        "(кожна модель з нового рядка)"
    )

    await state.set_state(AddUser.models)


# 4️⃣ МОДЕЛІ → ЗБЕРЕЖЕННЯ
@router.message(AddUser.models)
async def get_models(message: types.Message, state: FSMContext):
    text = message.text

    # 🔒 Валідація
    if "model:" not in text.lower():
        await message.answer("❌ Використай формат з 'Model:'")
        return

    lines = text.split("\n")

    current_brand = None
    data_dict = {}

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.lower().startswith("model:"):
            current_brand = line.split(":", 1)[1].strip()
            data_dict[current_brand] = []
        else:
            if current_brand:
                data_dict[current_brand].append(line)

    # зберігаємо
    await state.update_data(models=data_dict)
    data = await state.get_data()

    add_user(data)

    await message.answer("✅ Користувача додано")
    await state.clear()
