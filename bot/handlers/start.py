from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.states.seller import SellerStates
from bot.states.buyer import BuyerStates
from bot.database.db import cursor, conn

router = Router()

users = {}


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Обери хто ти:",
        reply_markup=role_keyboard()
    )


# вибір ролі
@router.callback_query()
async def handle_role(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if callback.data == "role_seller":
        users[user_id] = "seller"
        await callback.message.answer("Введи марку авто:")
        await state.set_state(SellerStates.waiting_for_brand)

    elif callback.data == "role_buyer":
        users[user_id] = "buyer"
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

    # DEBUG
    print("USERNAME:", username)

    cursor.execute(
        "INSERT INTO seller_cars (telegram_id, username, brand, model) VALUES (?, ?, ?, ?)",
        (user_id, username, brand, model)
    )
    conn.commit()

    # DEBUG
    cursor.execute("SELECT * FROM seller_cars")
    print("DB DATA:", cursor.fetchall())

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

    brand = data.get("brand")
    model = message.text

    cursor.execute(
        "SELECT DISTINCT telegram_id, username FROM seller_cars WHERE LOWER(brand)=? AND LOWER(model)=?",
        (brand.lower(), model.lower())
    )

    results = cursor.fetchall()

    if results:
        text = "Знайдені продавці:\n\n"
        for r in results:
            text += f"ID: {r[0]}\n"
            if r[1]:
                text += f"Username: @{r[1]}\n"
    else:
        text = "Нічого не знайдено ❌"

    await message.answer(text)
    await state.clear()
