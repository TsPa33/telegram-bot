from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.seller_menu import seller_menu_kb
from bot.utils.cache import get_cached_brands, get_cached_models

from bot.database.repositories.model_repo import (
    get_brands,
    get_models_by_brand,
    model_exists,
    get_model_id
)

from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    add_seller_car,
    delete_car,
    update_description
)

from bot.database.repositories.car_repo import get_seller_cars

from bot.keyboards.seller_inline import cars_list_kb, car_actions_kb

from bot.states.seller import SellerStates
from bot.utils.validation import validate_text, normalize_brand, normalize_model

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= MY CARS =================

@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):
    cars = await get_seller_cars(message.from_user.id)

    if not cars:
        await message.answer("❌ У вас немає авто")
        return

    await message.answer(
        "🚗 Обери авто:",
        reply_markup=cars_list_kb(cars)
    )


# ================= OPEN CAR =================

@router.callback_query(F.data.startswith("car_"))
async def open_car(callback: types.CallbackQuery):
    car_id = int(callback.data.split("_")[1])

    await callback.answer()

    await callback.message.answer(
        f"🚗 Авто ID: {car_id}",
        reply_markup=car_actions_kb(car_id)
    )


# ================= DELETE =================

@router.callback_query(F.data.startswith("delete_"))
async def delete_car_handler(callback: types.CallbackQuery):
    car_id = int(callback.data.split("_")[1])

    await delete_car(car_id)

    await callback.answer("Видалено")
    await callback.message.answer("❌ Авто видалено")


# ================= EDIT =================

@router.callback_query(F.data.startswith("edit_"))
async def edit_car_handler(callback: types.CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split("_")[1])

    await state.update_data(car_id=car_id)

    await callback.answer()
    await callback.message.answer("📝 Введи новий опис:")
    await state.set_state(SellerStates.description)


# ================= PROFILE =================

@router.message(F.text == "👤 Профіль")
async def seller_profile(message: Message):
    seller = await get_or_create_seller(
        message.from_user.id,
        message.from_user.username
    )

    cars = await get_seller_cars(message.from_user.id)

    text = (
        f"👤 <b>Твій профіль</b>\n\n"
        f"ID: {seller['id']}\n"
        f"Username: @{seller['username'] if seller['username'] else 'немає'}\n"
        f"🚗 Авто: {len(cars)}"
    )

    await message.answer(text, parse_mode="HTML")
