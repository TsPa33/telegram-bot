import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot.database.repositories.car_repo import (
    get_car_by_id,
    update_car_field
)

from bot.database.repositories.seller_repo import (
    get_seller_by_telegram_id,
    get_garage_info,
    get_seller_cars_by_seller_id,
    delete_car
)

from bot.keyboards.seller_inline import (
    cars_list_kb,
    seller_card_actions_kb
)

from bot.utils.formatters import format_car_card

router = Router()
logger = logging.getLogger(__name__)


# ================= STATES =================

class CarStates(StatesGroup):
    edit_photo = State()
    edit_description = State()


# ================= MY CARS =================

@router.message(F.text.in_(["📋 Мої авто", "📋 Мій гараж"]))
async def my_cars(message: Message):
    seller = await get_seller_by_telegram_id(message.from_user.id)

    if not seller:
        await message.answer("❌ Продавець не знайдений")
        return

    cars = await get_seller_cars_by_seller_id(seller["id"])

    garage_info = await get_garage_info(seller["id"])

    text = (
        "📋 Мій гараж\n\n"
        f"Всього місць: {garage_info.get('total', 0)}\n"
        f"Зайнято: {garage_info.get('used', 0)}\n"
        f"Вільно: {garage_info.get('free', 0)}\n\n"
        "🚗 Твої авто:"
    )

    await message.answer(text, reply_markup=cars_list_kb(cars))


# ================= OPEN CAR =================

@router.callback_query(F.data.startswith("car:"))
async def open_car(callback: CallbackQuery):
    car_id = int(callback.data.split(":")[1])
    car = await get_car_by_id(car_id)

    text = format_car_card(car, 1, 1, True)

    photo_id = car.get("photo_id")
    reply_markup = seller_card_actions_kb(car_id)

    if photo_id:
        try:
            await callback.message.answer_photo(
                photo=photo_id,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            return
        except TelegramBadRequest as exc:
            logger.warning("Seller car photo unavailable for car %s: %s", car_id, exc)

    await callback.message.answer(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


# ================= DELETE =================

@router.callback_query(F.data.startswith("delete:"))
async def delete_car_handler(callback: CallbackQuery):
    await callback.answer()

    car_id = int(callback.data.split(":")[1])

    await delete_car(car_id, callback.from_user.id)

    await callback.message.answer("✅ Авто видалено")


# ================= EDIT MENU =================

def car_edit_kb(car_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Змінити фото", callback_data=f"car_edit_photo:{car_id}")],
            [InlineKeyboardButton(text="📝 Змінити опис", callback_data=f"car_edit_desc:{car_id}")]
        ]
    )


@router.callback_query(F.data.startswith("car_edit:"))
async def edit_car_handler(callback: CallbackQuery):
    await callback.answer()

    car_id = int(callback.data.split(":")[1])

    await callback.message.answer(
        "✏️ Обери що змінити:",
        reply_markup=car_edit_kb(car_id)
    )


# ================= EDIT PHOTO =================

@router.callback_query(F.data.startswith("car_edit_photo:"))
async def edit_photo(callback: CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split(":")[1])

    await state.set_state(CarStates.edit_photo)
    await state.update_data(car_id=car_id)

    await callback.message.answer("📤 Надішли нове фото")


@router.message(CarStates.edit_photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    data = await state.get_data()

    photo_id = message.photo[-1].file_id

    await update_car_field(data["car_id"], "photo_id", photo_id)

    await state.clear()
    await message.answer("✅ Фото оновлено")


# ================= EDIT DESCRIPTION =================

@router.callback_query(F.data.startswith("car_edit_desc:"))
async def edit_desc(callback: CallbackQuery, state: FSMContext):
    car_id = int(callback.data.split(":")[1])

    await state.set_state(CarStates.edit_description)
    await state.update_data(car_id=car_id)

    await callback.message.answer("✏️ Введи новий опис")


@router.message(CarStates.edit_description)
async def save_desc(message: Message, state: FSMContext):
    data = await state.get_data()

    await update_car_field(
        data["car_id"],
        "description",
        message.text
    )

    await state.clear()
    await message.answer("✅ Опис оновлено")
