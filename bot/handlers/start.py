from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import F

from bot.keyboards.role import role_keyboard
from bot.keyboards.contact import contact_button
from bot.states.seller import SellerStates
from bot.states.buyer import BuyerStates
from bot.database.db import get_connection

router = Router()


# ================= START =================

from bot.keyboards.start import start_keyboard

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Натисни кнопку щоб почати:",
        reply_markup=start_keyboard()
    )


# ================= ROLE =================

@router.callback_query(F.data.in_(["role_seller", "role_buyer"]))
async def handle_role(callback: CallbackQuery, state: FSMContext):

    if callback.data == "role_seller":
        await callback.message.answer("Введи марку авто:")
        await state.set_state(SellerStates.waiting_for_brand)

    elif callback.data == "role_buyer":
        await callback.message.answer("Введи марку авто:")
        await state.set_state(BuyerStates.waiting_for_brand)

    await callback.answer()


# ================= SELLER =================

@router.message(SellerStates.waiting_for_brand)
async def seller_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text)
    await message.answer("Введи модель авто:")
    await state.set_state(SellerStates.waiting_for_model)


@router.message(SellerStates.waiting_for_model)
async def seller_model(message: Message, state: FSMContext):
    data = await state.get_data()

    user_id = message.from_user.id
    username = message.from_user.username

    brand = data.get("brand")
    model = message.text

    # нормалізація
    brand = brand.lower().strip()
    model = model.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO seller_cars (telegram_id, username, brand, model) VALUES (%s, %s, %s, %s)",
        (user_id, username, brand, model)
    )
    conn.commit()

    cursor.close()
    conn.close()

    await message.answer("Авто збережено в БД ✅")
    await state.clear()


# ================= BUYER =================

@router.message(BuyerStates.waiting_for_brand)
async def buyer_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text)
    await message.answer("Введи модель авто:")
    await state.set_state(BuyerStates.waiting_for_model)


@router.message(BuyerStates.waiting_for_model)
async def buyer_model(message: Message, state: FSMContext):
    data = await state.get_data()

    brand = data.get("brand").lower().strip()
    model = message.text.lower().strip()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT telegram_id, username, brand, model 
        FROM seller_cars 
        WHERE LOWER(brand)=%s AND LOWER(model)=%s
        """,
        (brand, model)
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

        await message.answer(
            text,
            reply_markup=contact_button(username if username else None)
        )

    await state.clear()
