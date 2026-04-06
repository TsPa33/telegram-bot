from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.keyboards.role import role_keyboard
from bot.keyboards.contact import contact_button
from bot.keyboards.start import start_keyboard

from bot.states.seller import SellerStates
from bot.states.buyer import BuyerStates
from bot.database.db import get_connection
from bot.keyboards.brands import brand_keyboard
from bot.keyboards.models import model_keyboard
router = Router()


# ================= START =================

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Натисни кнопку щоб почати:",
        reply_markup=start_keyboard()
    )


@router.message(F.text == "Поїхали 🚀")
async def start_button(message: Message):
    await message.answer(
        "Обери хто ти:",
        reply_markup=role_keyboard()
    )


# ================= ROLE =================

@router.callback_query(F.data == "role_seller")
async def handle_seller(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Обери марку авто:",
        reply_markup=brand_keyboard()
    )
    await state.set_state(SellerStates.waiting_for_brand)
    await callback.answer()


@router.callback_query(F.data == "role_buyer")
async def handle_buyer(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Обери марку авто:",
        reply_markup=brand_keyboard()
    )
    await state.set_state(BuyerStates.waiting_for_brand)
    await callback.answer()


# ================= VALIDATION маршутизована в іншу папку =================




# ================= SELLER ================ #



# ================= BUYER =================

