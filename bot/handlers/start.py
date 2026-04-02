from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.states.seller import SellerStates

router = Router()

users = {}


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Обери хто ти:",
        reply_markup=role_keyboard()
    )


@router.callback_query()
async def handle_role(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if callback.data == "role_seller":
        users[user_id] = "seller"

        await callback.message.answer("Введи марку авто:")
        await state.set_state(SellerStates.waiting_for_brand)

    elif callback.data == "role_buyer":
        users[user_id] = "buyer"
        await callback.message.answer("Ти обрав: Покупець")

    await callback.answer()


# ввод марки
@router.message(SellerStates.waiting_for_brand)
async def get_brand(message: Message, state: FSMContext):
    await state.update_data(brand=message.text)

    await message.answer("Введи модель авто:")
    await state.set_state(SellerStates.waiting_for_model)


# ввод моделі
@router.message(SellerStates.waiting_for_model)
async def get_model(message: Message, state: FSMContext):
    data = await state.get_data()

    brand = data.get("brand")
    model = message.text

    await message.answer(
        f"Збережено:\nМарка: {brand}\nМодель: {model}"
    )

    await state.clear()
