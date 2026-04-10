from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import ReplyKeyboardRemove

from bot.database.db import get_brands, get_models_by_brand, find_by_model
from bot.states.buyer_states import Buyer

router = Router()


# 🔹 старт пошуку
@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await message.answer(
    "Оновлюю меню...",
    reply_markup=ReplyKeyboardRemove()
)
    brands = get_brands()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands],
        resize_keyboard=True
    )

    await message.answer("Обери бренд:", reply_markup=keyboard)
    await state.set_state(Buyer.brand)


# 🔹 вибір бренду
@router.message(Buyer.brand)
async def choose_brand(message: types.Message, state: FSMContext):
    brand = message.text

    models = get_models_by_brand(brand)

    if not models:
        await message.answer("❌ Моделей немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)
    await message.answer("Обери модель:", reply_markup=keyboard)
    await state.set_state(Buyer.model)


# 🔹 вибір моделі → результат
@router.message(Buyer.model)
async def choose_model(message: types.Message, state: FSMContext):
    model = message.text

    data = await state.get_data()
    brand = data["brand"]

    results = find_by_model(brand, model)

    if not results:
        await message.answer("❌ Нічого не знайдено")
        return

    text = ""

    for name, website, phone in results:
        text += f"{name}\n{website}\n{phone}\n\n"

    await message.answer(text)
    await state.clear()
