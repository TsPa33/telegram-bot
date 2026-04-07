from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from bot.states.seller import SellerStates
from bot.database.db import get_connection
from bot.keyboards.models import model_keyboard
from bot.utils.validation import validate_text, normalize

router = Router()


@router.message(SellerStates.waiting_for_brand, F.text)
async def seller_brand(message: Message, state: FSMContext):
    print("BUYER BRAND:", message.text)

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

    cursor.execute(
    """
    INSERT INTO seller_cars (telegram_id, username, brand, model)
    VALUES (%s, %s, %s, %s)
    """,
    (user_id, username, brand, model)
)

    conn.commit()

    await message.answer("Авто збережено в БД ✅")

    cursor.close()
    conn.close()

    await state.clear()
