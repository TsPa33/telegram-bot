from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from bot.database.repositories.model_repo import get_brands
from bot.utils.cache import get_cached_brands

from bot.states.buyer_states import Buyer


router = Router()

BACK = KeyboardButton(text="⬅️ Назад")


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_cached_brands(get_brands)

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(Buyer.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= GLOBAL BACK =================

@router.message(F.text == "⬅️ Назад")
async def global_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        await message.answer("🔙 Головне меню")
        return

    if current_state == Buyer.model:
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(Buyer.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    if current_state == Buyer.brand:
        await state.clear()
        await message.answer("🔙 Головне меню")
        return

    await state.clear()
    await message.answer("🔙 Головне меню")
