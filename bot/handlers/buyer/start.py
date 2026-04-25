from aiogram import Router, types, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from bot.database.repositories.model_repo import get_brands_with_ids
from bot.keyboards.brands import brand_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.buyer_reply import buyer_reply_kb
from bot.states.buyer_states import Buyer

router = Router()


# ================= BUYER HOME =================

PHOTO_ID = "AgACAgIAAxkBAAInT2ns1VVBPxs6dClg_laFO2xhDoxmAAJbFGsb1aVhS1XfR9RQ5x8VAQADAgADeQADOwQ"


async def show_buyer_home(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 FIX

    await message.answer_photo(
        photo=PHOTO_ID,
        reply_markup=buyer_home_kb(),
    )

    await message.answer(
        "Швидкий доступ до меню:",
        reply_markup=buyer_reply_kb()
    )


# ================= RESTART BUTTON =================

from bot.keyboards.main_menu import main_menu_kb


@router.message(F.text == "🔄 Оновити Bot")
async def restart_bot(message: types.Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(message.from_user.id),
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


@router.callback_query(F.data == "buyer:views")
async def buyer_views_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("👀 Мої перегляди будуть доступні скоро.")


@router.callback_query(F.data == "buyer:favorites")
async def buyer_favorites_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("⭐ Обрані будуть доступні скоро.")


@router.callback_query(F.data == "buyer:profile")
async def buyer_profile_handler(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("👤 Профіль покупця буде доступний скоро.")


# ================= SEARCH FLOW =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 FIX

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
