from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.states.buyer import BuyerStates
from bot.database.db import get_connection
from bot.keyboards.models import model_keyboard
from bot.keyboards.contact import contact_button
from bot.utils.validation import validate_text, normalize

router = Router()


# ✅ BRAND
@router.message(BuyerStates.waiting_for_brand, F.text)
async def buyer_brand(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна марка ❗")
        return

    brand = message.text

    await state.update_data(brand=brand)

    await message.answer(
        "Обери модель:",
        reply_markup=model_keyboard(brand)
    )

    await state.set_state(BuyerStates.waiting_for_model)


# ✅ MODEL (ВИПРАВЛЕНО STATE)
@router.message(BuyerStates.waiting_for_model, F.text)
async def buyer_model(message: Message, state: FSMContext):

    print("BUYER MODEL TRIGGERED")

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
