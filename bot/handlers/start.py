from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.states.seller import SellerStates
from bot.states.buyer import BuyerStates

router = Router()

users = {}
sellers = []


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

    seller_data = {
        "user_id": message.from_user.id,
        "brand": data.get("brand"),
        "model": message.text
    }

    sellers.append(seller_data)

    await message.answer("Авто збережено ✅")
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

    # пошук продавців
    found = [
        s for s in sellers
        if s["brand"].lower() == brand.lower()
        and s["model"].lower() == model.lower()
    ]

    if found:
        text = "Знайдені продавці:\n\n"
        for s in found:
            text += f"ID: {s['user_id']}\n"
    else:
        text = "Нічого не знайдено ❌"

    await message.answer(text)
    await state.clear()
