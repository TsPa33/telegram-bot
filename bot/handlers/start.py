from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.config import is_admin
from bot.handlers.admin import show_admin_panel
from bot.handlers.buyer.start import start_buyer
from bot.keyboards.main_menu import main_menu_kb
from bot.keyboards.seller_menu import seller_menu_kb


router = Router()


@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer(
        "🔹 Обери дію",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


@router.callback_query(F.data == "nav:home")
async def home(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)
    await callback.message.answer(
        "🔹 Обери дію",
        reply_markup=await main_menu_kb(callback.from_user.id),
    )


@router.callback_query(F.data == "nav:seller")
@router.callback_query(F.data == "nav:garage")
async def open_seller(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)
    await callback.message.answer(
        "🏪 Режим продавця\nОберіть дію:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.message.answer(
        "Меню продавця:",
        reply_markup=seller_menu_kb(),
    )


@router.callback_query(F.data == "nav:admin")
async def open_admin(callback: CallbackQuery):
    await callback.answer()
    if not is_admin(callback.from_user.id):
        await callback.answer("Немає доступу", show_alert=True)
        return
    await show_admin_panel(callback.message)


@router.message(F.text == "Поїхали 🚀")
async def start_button(message: Message, state: FSMContext):
    await state.set_state(None)
    await message.answer("Оновлюю меню...", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "🔹 Обери дію",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


@router.callback_query(F.data == "role_buyer")
@router.callback_query(F.data == "role_seller")
async def legacy_role_callbacks(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(None)
    if callback.data == "role_buyer":
        await start_buyer(callback.message, state)
        return

    await callback.message.answer(
        "Меню продавця:",
        reply_markup=seller_menu_kb(),
    )
