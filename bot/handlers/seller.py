from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.states.seller import SellerStates
from bot.database.db import get_connection
from bot.keyboards.models import model_keyboard
from bot.keyboards.brands import brand_keyboard
from bot.utils.validation import validate_text, normalize

router = Router()


# ================= SELLER MENU =================

@router.message(F.text == "➕ Додати авто")
async def add_car_start(message: Message, state: FSMContext):
    await message.answer(
        "Обери марку авто:",
        reply_markup=brand_keyboard()
    )
    await state.set_state(SellerStates.waiting_for_brand)


@router.message(F.text == "📋 Мої авто")
async def my_cars(message: Message):

    user_id = message.from_user.id

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT sc.brand, sc.model, sc.photo_id
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        WHERE s.telegram_id = %s
        """,
        (user_id,)
    )

    cars = cursor.fetchall()

    cursor.close()
    conn.close()

    if not cars:
        await message.answer("У вас ще немає авто ❗")
        return

    for brand, model, photo_id in cars:
        text = f"🚗 {brand} {model}"

        if photo_id:
            await message.answer_photo(photo_id, caption=text)
        else:
            await message.answer(text)


@router.message(F.text == "👤 Профіль")
async def profile(message: Message):

    user_id = message.from_user.id

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, company_name, phone, telegram_link, city, views, clicks
    FROM sellers
    WHERE telegram_id = %s
    """, (user_id,))

    seller = cursor.fetchone()

    cursor.close()
    conn.close()

    if not seller:
        await message.answer("Профіль не знайдено ❗")
        return

    name, company, phone, link, city, views, clicks = seller

    text = "👤 Профіль:\n\n"
    text += f"👁 Перегляди: {views}\n"
    text += f"🔗 Переходи: {clicks}\n\n"

    if company:
        text += f"🏪 {company}\n"
    if name:
        text += f"👤 {name}\n"
    if city:
        text += f"📍 {city}\n"
    if phone:
        text += f"📞 {phone}\n"
    if link:
        text += f"🔗 {link}\n"

    await message.answer(text)


# ================= FSM =================

@router.message(SellerStates.waiting_for_brand, F.text)
async def seller_brand(message: Message, state: FSMContext):

    if message.text in ["➕ Додати авто", "📋 Мої авто", "👤 Профіль"]:
        return

    if not validate_text(message.text):
        await message.answer("Некоректна марка ❗")
        return

    await state.update_data(brand=message.text)

    await message.answer(
        "Обери модель:",
        reply_markup=model_keyboard(message.text)
    )

    await state.set_state(SellerStates.waiting_for_model)


@router.message(SellerStates.waiting_for_model, F.text)
async def seller_model(message: Message, state: FSMContext):

    if message.text in ["➕ Додати авто", "📋 Мої авто", "👤 Профіль"]:
        return

    if not validate_text(message.text):
        await message.answer("Некоректна модель ❗")
        return

    await state.update_data(model=message.text)

    data = await state.get_data()

    user_id = message.from_user.id
    username = message.from_user.username

    brand = normalize(data.get("brand"))
    model = normalize(data.get("model"))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM sellers WHERE telegram_id = %s",
        (user_id,)
    )
    seller = cursor.fetchone()

    if not seller:
        cursor.execute(
            """
            INSERT INTO sellers (telegram_id, username)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, username)
        )
        seller_id = cursor.fetchone()[0]
    else:
        seller_id = seller[0]

    # 🔥 ЗБЕРІГАЄМО АВТО
    cursor.execute(
        """
        INSERT INTO seller_cars (seller_id, brand, model)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (seller_id, brand, model)
    )

    result = cursor.fetchone()

    if not result:
        await message.answer("Таке авто вже існує ❗")
        cursor.close()
        conn.close()
        await state.clear()
        return

    # 🔥 ДОДАЄМО В models (для buyer)
    cursor.execute(
        """
        INSERT INTO models (user_id, brand, model)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (seller_id, brand, model)
    )

    conn.commit()

    await message.answer("Авто збережено в БД ✅")

    cursor.close()
    conn.close()

    await state.clear()
