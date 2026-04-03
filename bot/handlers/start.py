from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.keyboards.contact import contact_button
from bot.keyboards.start import start_keyboard

from bot.states.seller import SellerStates
from bot.states.buyer import BuyerStates
from bot.database.db import get_connection
from bot.keyboards.brands import brand_keyboard
router = Router()


# ================= START =================

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Натисни кнопку щоб почати:",
        reply_markup=start_keyboard()
    )


@router.message(F.text == "Поїхали 🚀")
async def start_button(message: Message):
    await message.answer(
        "Обери хто ти:",
        reply_markup=role_keyboard()
    )


# ================= ROLE =================

@router.callback_query(F.data == "role_seller")
async def handle_seller(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Обери марку авто:",
        reply_markup=brand_keyboard()
    )
    await state.set_state(SellerStates.waiting_for_brand)
    await callback.answer()


@router.callback_query(F.data == "role_buyer")
async def handle_buyer(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Обери марку авто:",
        reply_markup=brand_keyboard()
    )
    await state.set_state(BuyerStates.waiting_for_brand)
    await callback.answer()


# ================= VALIDATION =================

def validate_text(text: str):
    return text and text.strip()


def normalize(text: str):
    return text.lower().strip().capitalize()


# ================= SELLER =================

@from bot.keyboards.models import model_keyboard

@router.message(SellerStates.waiting_for_brand)
async def seller_brand(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна марка ❗")
        return

    brand = message.text

    await state.update_data(brand=brand)

    await message.answer(
        "Обери модель:",
        reply_markup=model_keyboard(brand)
    )

    await state.set_state(SellerStates.waiting_for_model)

@router.message(SellerStates.waiting_for_model)
async def seller_model(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна модель ❗")
        return

    data = await state.get_data()

    user_id = message.from_user.id
    username = message.from_user.username

    brand = normalize(data.get("brand"))
    model = normalize(message.text)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO seller_cars (telegram_id, username, brand, model)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (telegram_id, brand, model) DO NOTHING
        """,
        (user_id, username, brand, model)
    )

    conn.commit()

    if cursor.rowcount == 0:
        await message.answer("Таке авто вже додано ❗")
    else:
        await message.answer("Авто збережено в БД ✅")

    cursor.close()
    conn.close()

    await state.clear()


# ================= BUYER =================

@router.message(BuyerStates.waiting_for_brand)
async def buyer_brand(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна марка ❗")
        return

    await state.update_data(brand=message.text)
    await message.answer("Введи модель авто:")
    await state.set_state(BuyerStates.waiting_for_model)


@router.message(BuyerStates.waiting_for_model)
async def buyer_model(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна модель ❗")
        return

    data = await state.get_data()

    brand = normalize(data.get("brand"))
    model = normalize(message.text)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT telegram_id, username, brand, model 
        FROM seller_cars 
        WHERE LOWER(brand)=%s AND LOWER(model)=%s
        """,
        (brand.lower(), model.lower())
    )

    results = cursor.fetchall()

    cursor.close()
    conn.close()

    if not results:
        await message.answer("Нічого не знайдено ❌")
        await state.clear()
        return

    sellers_dict = {}

    for user_id, username, brand, model in results:
        if user_id not in sellers_dict:
            sellers_dict[user_id] = {
                "username": username,
                "cars": []
            }

        sellers_dict[user_id]["cars"].append(f"{brand} {model}")

    for user_id, data in sellers_dict.items():
        username = data["username"]
        cars = data["cars"]

        text = "Продавець:\n"

        if username:
            text += f"@{username}\n\n"
        else:
            text += f"ID: {user_id}\n\n"

        text += "Авто:\n"
        for car in cars:
            text += f"- {car}\n"

        reply_markup = contact_button(username) if username else None

        await message.answer(
            text,
            reply_markup=reply_markup
        )

    await state.clear()
