from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.states.buyer import BuyerStates
from bot.database.db import get_connection
from bot.keyboards.models import model_keyboard
from bot.keyboards.contact import contact_button
from bot.utils.validation import validate_text, normalize

router = Router()


# ================= BRAND =================

@router.message(BuyerStates.waiting_for_brand, F.text)
async def buyer_brand(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна марка ❗")
        return

    await state.update_data(brand=message.text)

    await message.answer(
        "Обери модель:",
        reply_markup=model_keyboard(message.text)
    )

    await state.set_state(BuyerStates.waiting_for_model)


# ================= MODEL + SEARCH =================

@router.message(BuyerStates.waiting_for_model, F.text)
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
        SELECT 
            s.id,
            s.telegram_id,
            s.username,
            s.name,
            s.company_name,
            s.phone,
            s.telegram_link,
            s.city,
            sc.brand,
            sc.model
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        WHERE LOWER(sc.brand) = %s AND LOWER(sc.model) = %s
        """,
        (brand.lower(), model.lower())
    )

    results = cursor.fetchall()

    if not results:
        await message.answer("Нічого не знайдено ❌")
        await state.clear()
        cursor.close()
        conn.close()
        return

    # ================= +1 VIEW =================
    for row in results:
        seller_id = row[0]

        cursor.execute(
            "UPDATE sellers SET views = views + 1 WHERE id = %s",
            (seller_id,)
        )

    conn.commit()

    # ================= GROUP =================
    sellers_dict = {}

    for (
        seller_id,
        telegram_id,
        username,
        name,
        company_name,
        phone,
        telegram_link,
        city,
        brand,
        model
    ) in results:

        if seller_id not in sellers_dict:
            sellers_dict[seller_id] = {
                "telegram_id": telegram_id,
                "username": username,
                "name": name,
                "company_name": company_name,
                "phone": phone,
                "telegram_link": telegram_link,
                "city": city,
                "cars": []
            }

        sellers_dict[seller_id]["cars"].append(f"{brand} {model}")

    # ================= OUTPUT =================
    for seller_id, data in sellers_dict.items():

        username = data["username"]
        name = data["name"]
        company_name = data["company_name"]
        phone = data["phone"]
        telegram_link = data["telegram_link"]
        city = data["city"]
        cars = data["cars"]

        text = ""

        if company_name:
            text += f"🏪 {company_name}\n"

        if name:
            text += f"👤 {name}\n"

        if city:
            text += f"📍 {city}\n"

        text += "\n🚗 Авто:\n"
        for car in cars:
            text += f"- {car}\n"

        text += "\n"

        if phone:
            text += f"📞 {phone}\n"

        if username:
            text += f"💬 @{username}\n"

        if telegram_link:
            text += f"🔗 {telegram_link}\n"

        await message.answer(
            text,
            reply_markup=contact_button(seller_id)
        )

    cursor.close()
    conn.close()

    await state.clear()


# ================= CONTACT CLICK =================

@router.callback_query(F.data.startswith("contact_"))
async def contact_click(callback: CallbackQuery):

    seller_id = int(callback.data.split("_")[1])

    conn = get_connection()
    cursor = conn.cursor()

    # +1 CLICK
    cursor.execute(
        "UPDATE sellers SET clicks = clicks + 1 WHERE id = %s",
        (seller_id,)
    )

    # отримати username
    cursor.execute(
        "SELECT username FROM sellers WHERE id = %s",
        (seller_id,)
    )
    user = cursor.fetchone()

    conn.commit()
    cursor.close()
    conn.close()

    if user and user[0]:
        await callback.message.answer(f"https://t.me/{user[0]}")
    else:
        await callback.message.answer("Контакт недоступний")

    await callback.answer()
