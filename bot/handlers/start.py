from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.keyboards.main_menu import main_menu_kb
from bot.keyboards.seller_menu import seller_menu_kb
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import demo_categories_kb, demo_group_kb

from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.user_repo import log_visit, create_user

from bot.services.roles import is_admin
from bot.services.site_packages import get_demo_group

router = Router()


# ================= GLOBAL RESET =================

@router.message(F.text == "🔄 Оновити Bot")
async def global_restart(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


# ================= GLOBAL HOME =================

@router.message(F.text == "↩️ На головне меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


# ================= START =================

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()

    # 🔥 СТВОРЕННЯ USER (КРИТИЧНО)
    await create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )

    # ✅ LOG VISIT
    await log_visit(message.from_user, role="unknown")

    await message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


# ================= ROLE SELLER =================

@router.callback_query(F.data == "role:seller")
async def enter_seller(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    # 🔥 СТВОРЕННЯ USER
    await create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username
    )

    # ✅ LOG VISIT
    await log_visit(callback.from_user, role="seller")

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
        reply_markup=seller_menu_kb(
            is_verified=seller.get("is_verified", False)
        ),
    )


# ================= SELLER NAV =================

@router.callback_query(F.data.in_(["nav:seller", "nav:garage"]))
async def open_seller(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    await create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username
    )

    await log_visit(callback.from_user, role="seller")

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
        reply_markup=seller_menu_kb(
            is_verified=seller.get("is_verified", False)
        ),
    )


# ================= ADMIN =================

@router.callback_query(F.data == "nav:admin")
async def open_admin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    if not await is_admin(callback.from_user.id):
        await callback.message.answer("❌ Немає доступу")
        return

    await callback.message.answer(
        "⚙️ Панель адміністратора",
        reply_markup=admin_kb
    )


# ================= DEMO SITES =================

@router.callback_query(F.data == "demo:sites")
async def demo_sites(callback: CallbackQuery):
    await callback.answer()

    await callback.message.answer(
        "🌐 <b>Демо сайти Carpot</b>\n\n"
        "Оберіть категорію demo сайту або перейдіть до замовлення:",
        parse_mode="HTML",
        reply_markup=demo_categories_kb(),
    )


@router.callback_query(F.data.startswith("demo:category:"))
async def demo_category(callback: CallbackQuery):
    group_key = callback.data.split(":")[-1]
    group = get_demo_group(group_key)

    if not group:
        await callback.answer("Категорію не знайдено", show_alert=True)
        return

    demos_text = "\n".join(
        f"• {demo['button_text']} — {demo['description']}"
        for demo in group["demos"]
    )

    text = (
        f"{group['emoji']} <b>{group['title']}</b>\n\n"
        f"{group['description']}\n\n"
        f"{demos_text}"
    )

    if callback.message.text:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=demo_group_kb(group_key),
        )
    else:
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=demo_group_kb(group_key),
        )
    await callback.answer()


@router.callback_query(F.data == "demo:back")
async def demo_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(callback.from_user.id),
    )
    await callback.answer()
