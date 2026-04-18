from aiogram import Router, types
from aiogram.filters import Command
from aiogram import F
from aiogram.fsm.context import FSMContext

from bot.database.repositories.model_repo import get_brands_with_ids
from bot.keyboards.brands import brand_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.states.buyer_states import Buyer


router = Router()


async def show_buyer_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏠 <b>Головне меню покупця</b>\n\n"
        "👤 Профіль\n"
        "🚗 Знайти авто\n"
        "👀 Мої перегляди\n"
        "⭐ Обрані",
        parse_mode="HTML",
        reply_markup=buyer_home_kb(),
    )


@router.message(Command("start"))
async def buyer_home_start(message: types.Message, state: FSMContext):
    await show_buyer_home(message, state)


@router.callback_query(F.data == "nav:home")
async def buyer_home_callback(callback: types.CallbackQuery, state: FSMContext):
    print("NAV:", callback.data)
    await callback.answer()
    await show_buyer_home(callback.message, state)


@router.callback_query(F.data == "buyer:find")
async def buyer_find_handler(callback: types.CallbackQuery, state: FSMContext):
    print("NAV:", callback.data)
    await callback.answer()
    await start_buyer(callback.message, state)


@router.callback_query(F.data == "buyer:views")
async def buyer_views_handler(callback: types.CallbackQuery):
    print("NAV:", callback.data)
    await callback.answer()
    await callback.message.answer("👀 Мої перегляди будуть доступні скоро.")


@router.callback_query(F.data == "buyer:favorites")
async def buyer_favorites_handler(callback: types.CallbackQuery):
    print("NAV:", callback.data)
    await callback.answer()
    await callback.message.answer("⭐ Обрані будуть доступні скоро.")


@router.callback_query(F.data == "buyer:profile")
async def buyer_profile_handler(callback: types.CallbackQuery):
    print("NAV:", callback.data)
    await callback.answer()
    await callback.message.answer("👤 Профіль покупця буде доступний скоро.")


@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_brands_with_ids()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    await state.set_state(Buyer.brand)
    print("STATE SET TO Buyer.brand")
    await message.answer("🚗 Обери бренд", reply_markup=brand_kb(brands))
