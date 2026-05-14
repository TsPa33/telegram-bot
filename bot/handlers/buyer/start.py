import logging
import os

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.database.repositories.model_repo import get_brands_with_ids
from bot.keyboards.brands import brand_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.buyer_reply import buyer_reply_kb
from bot.states.buyer_states import Buyer

from bot.keyboards.main_menu import main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


# ================= BUYER HOME =================

BUYER_HOME_TEXT = "🚗 Твій автомобільний асистент\n\nОбери, що потрібно зараз:"
BUYER_HOME_IMAGE_URL = os.getenv("BUYER_HOME_IMAGE_URL")


async def show_buyer_home(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 гарантія чистого входу

    if BUYER_HOME_IMAGE_URL:
        try:
            await message.answer_photo(
                photo=BUYER_HOME_IMAGE_URL,
                caption=BUYER_HOME_TEXT,
                reply_markup=buyer_home_kb(),
            )
        except TelegramBadRequest as exc:
            logger.warning("Buyer home image unavailable: %s", exc)
            await message.answer(
                BUYER_HOME_TEXT,
                reply_markup=buyer_home_kb(),
            )
    else:
        await message.answer(
            BUYER_HOME_TEXT,
            reply_markup=buyer_home_kb(),
        )

    await message.answer(
        "Швидкий доступ до меню:",
        reply_markup=buyer_reply_kb()
    )


# ================= ROLE ENTRY =================

@router.callback_query(F.data == "role:buyer")
async def enter_buyer(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_buyer_home(callback.message, state)


# ================= NAV =================

@router.callback_query(F.data == "nav:home")
async def buyer_home_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_buyer_home(callback.message, state)


# ================= BUYER ACTIONS =================

@router.callback_query(F.data == "buyer:find")
async def buyer_find_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_buyer(callback.message, state)


# ================= SEARCH FLOW =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 ізоляція flow

    brands = await get_brands_with_ids()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    await state.set_state(Buyer.brand)

    await message.answer(
        "🔎 Переходимо до пошуку...",
        reply_markup=buyer_reply_kb(),
    )

    await message.answer(
        "🚗 Обери бренд",
        reply_markup=brand_kb(brands)
    )
