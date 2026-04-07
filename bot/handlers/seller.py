from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.states.seller import SellerStates
from bot.database.db import get_connection
from bot.keyboards.models import model_keyboard
from bot.utils.validation import validate_text, normalize

router = Router()


# ================= SELLER ADD CAR =================

@router.message(SellerStates.waiting_for_brand, F.text)
async def seller_brand(message: Message, state: FSMContext):

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

    # 🔹 знайти seller
    cursor.execute(
        "SELECT id FROM sellers WHERE telegram_id = %s",
        (user_id,)
    )
    seller = cursor.fetchone()

    # 🔹 якщо нема — створити
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

    # 🔹 додати авто
    cursor.execute(
        """
        INSERT INTO seller_cars (seller_id, brand, model)
        VALUES (%s, %s, %s)
        """,
        (seller_id, brand, model)
    )

    conn.commit()

    await message.answer("Авто збережено в БД ✅")

    cursor.close()
    conn.close()

    await state.clear()


# ================= SELLER REGISTRATION =================

@router.message(F.text == "Реєстрація продавця")
async def start_registration(message: Message, state: FSMContext):
    await message.answer("Введи своє імʼя:")
    await state.set_state(SellerStates.reg_name)


@router.message(SellerStates.reg_name, F.text)
async def reg_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)

    await message.answer("Назва розборки:")
    await state.set_state(SellerStates.reg_company)


@router.message(SellerStates.reg_company, F.text)
async def reg_company(message: Message, state: FSMContext):
    await state.update_data(company=message.text)

    await message.answer("Телефон:")
    await state.set_state(SellerStates.reg_phone)


@router.message(SellerStates.reg_phone, F.text)
async def reg_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)

    await message.answer("Telegram або сайт:")
    await state.set_state(SellerStates.reg_link)


@router.message(SellerStates.reg_link, F.text)
async def reg_link(message: Message, state: FSMContext):
    await state.update_data(link=message.text)

    await message.answer("Місто:")
    await state.set_state(SellerStates.reg_city)


@router.message(SellerStates.reg_city, F.text)
async def reg_city(message: Message, state: FSMContext):

    data = await state.get_data()

    user_id = message.from_user.id
    username = message.from_user.username

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO sellers (
            telegram_id, username, name, company_name, phone, telegram_link, city
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (telegram_id)
        DO UPDATE SET
            name = EXCLUDED.name,
            company_name = EXCLUDED.company_name,
            phone = EXCLUDED.phone,
            telegram_link = EXCLUDED.telegram_link,
            city = EXCLUDED.city
        """,
        (
            user_id,
            username,
            data.get("name"),
            data.get("company"),
            data.get("phone"),
            data.get("link"),
            message.text
        )
    )

    conn.commit()
    cursor.close()
    conn.close()

    await message.answer("Профіль збережено ✅")

    await state.clear()
