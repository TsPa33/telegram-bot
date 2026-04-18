from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.keyboards.seller_menu import seller_menu_kb

from bot.handlers.buyer.start import start_buyer, show_buyer_home

router = Router()


# ================= START =================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await show_buyer_home(message, state)


@router.message(F.text == "Поїхали 🚀")
async def start_button(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "Оновлюю меню...",
        reply_markup=ReplyKeyboardRemove()
    )

    await message.answer(
        "Обери хто ти:",
        reply_markup=role_keyboard()
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
        reply_markup=seller_menu_kb()
    )
    await callback.answer()
