from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.keyboards.start import start_keyboard
from bot.keyboards.seller_menu import seller_menu

from bot.handlers.buyer import start_buyer

router = Router()


# ================= START =================

@router.message(Command("start"))
async def cmd_start(message: Message):
    await state.clear()
    
    await message.answer(
        "Натисни кнопку щоб почати:",
        reply_markup=start_keyboard()
    )


@router.message(F.text == "Поїхали 🚀")
async def start_button(message: Message):
    await message.answer(
        "Обери хто ти:",
        reply_markup=start_keyboard(message.from_user.id)
    )


# ================= ROLE =================

# 🟢 ПОКУПЕЦЬ — використовуємо існуючу логіку з buyer.py
@router.callback_query(F.data == "role_buyer")
async def handle_buyer(callback: CallbackQuery, state: FSMContext):
    await start_buyer(callback.message, state)
    await callback.answer()


# 🟢 ПРОДАВЕЦЬ — відкриваємо меню
@router.callback_query(F.data == "role_seller")
async def handle_seller(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Меню продавця:",
        reply_markup=seller_menu()
    )
    await callback.answer()
