from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.handlers.buyer.start import start_buyer
from bot.keyboards.main_menu import main_menu_kb
from bot.keyboards.seller_menu import seller_menu_kb
from bot.keyboards.admin_kb import admin_kb
from bot.database.repositories.seller_repo import get_or_create_seller

router = Router()


@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer(
        "🔹 Обери дію",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


# ================= SELLER =================

@router.callback_query(F.data == "nav:seller")
@router.callback_query(F.data == "nav:garage")
async def open_seller(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)

    seller = await get_or_create_seller(
        callback.from_user.id,
        callback.from_user.username
    )

    await callback.message.answer(
        "🏪 Режим продавця\nОберіть дію:",
        reply_markup=ReplyKeyboardRemove(),
    )

    await callback.message.answer(
        "Меню продавця:",
        reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)),
    )


@router.callback_query(F.data == "role_seller")
async def legacy_role_callbacks(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)

    seller = await get_or_create_seller(
        callback.from_user.id,
        callback.from_user.username
    )

    await callback.message.answer(
        "Меню продавця:",
        reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False)),
    )


# ================= ADMIN =================

@router.callback_query(F.data == "nav:admin")  # ✅ FIX
async def open_admin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)

    ADMIN_IDS = [6206952389]

    if callback.from_user.id not in ADMIN_IDS:
        await callback.message.answer("❌ Немає доступу")
        return

    await callback.message.answer(
        "⚙️ Панель адміністратора",
        reply_markup=admin_kb
    )
