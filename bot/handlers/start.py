from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove

from bot.keyboards.main_menu import main_menu_kb
from bot.keyboards.seller_menu import seller_menu_kb
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import demo_categories_kb, demo_group_kb

from bot.database.base import fetchrow
from bot.database.repositories.analytics_repo import upsert_telegram_attribution
from bot.database.repositories.crm_admin_repo import list_admin_users
from bot.database.repositories.promo_repo import (
    START_PROMO_CODE,
    activate_start_promo,
    get_promo_activation,
)
from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.user_repo import log_visit, create_user

from bot.config import ADMIN_IDS
from bot.keyboards.profile_inline import profile_edit_kb
from bot.services.roles import is_admin
from bot.services.site_packages import get_demo_group

router = Router()


def _start_payload(message: Message) -> str:
    parts = (message.text or "").strip().split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _promo_profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Заповнити профіль", callback_data="promo:fill_profile")],
        ]
    )


def _promo_activation_text() -> str:
    return (
        "✅ Вам активовано стартовий пакет CarPot на 3 місяці.\n\n"
        "Що входить:\n"
        "• Сайт для автобізнесу\n"
        "• Telegram-керування\n"
        "• Прийом заявок\n"
        "• Базовий дизайн\n"
        "• Допомога з запуском реклами\n\n"
        "Наступний крок:\n"
        "Заповніть профіль та інформацію про свій бізнес.\n\n"
        "Для запуску реклами з вами звʼяжеться менеджер CarPot "
        "і допоможе з базовим налаштуванням."
    )


async def _notify_admins_about_start_promo(bot, user, activation) -> None:
    username = f"@{user.username}" if user.username else "—"
    activated_at = activation.get("activated_at")
    activated_at_text = activated_at.strftime("%d.%m.%Y %H:%M") if activated_at else "—"

    text = (
        "🟢 <b>Новий безпечний старт CarPot</b>\n\n"
        "Користувач активував /start START.\n"
        "Потрібно звʼязатися для профілю та запуску реклами.\n\n"
        f"Telegram ID: <code>{user.id}</code>\n"
        f"Username: {username}\n"
        f"Promo code: {activation.get('promo_code', START_PROMO_CODE)}\n"
        f"Activation date: {activated_at_text}"
    )

    admin_ids = set(ADMIN_IDS)
    try:
        admin_rows = await list_admin_users()
        admin_ids.update(
            row["telegram_id"]
            for row in admin_rows
            if row.get("is_active") and row.get("role") in {"super_admin", "admin", "manager"}
        )
    except Exception as e:
        print("ERROR LOAD ADMINS FOR START PROMO:", e)

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            print("ERROR SEND START PROMO ADMIN NOTIFY:", admin_id, e)


async def _get_seller_profile(telegram_id: int):
    return await fetchrow(
        """
        SELECT id, shop_name, name, phone, website, city, description, photo_id, is_verified
        FROM sellers
        WHERE telegram_id = $1
        LIMIT 1
        """,
        telegram_id,
    )


def _render_seller_profile(seller) -> str:
    verified = seller.get("is_verified") if seller else False
    status = "✅ Верифіковано" if verified else "❌ Не верифіковано"

    return (
        "👤 <b>Профіль продавця</b>\n\n"
        f"🔐 {status}\n\n"
        f"🏪 {seller.get('shop_name') or '-'}\n"
        f"👤 {seller.get('name') or '-'}\n"
        f"📞 {seller.get('phone') or '-'}\n"
        f"🌐 {seller.get('website') or '-'}\n"
        f"📍 {seller.get('city') or '-'}\n"
        f"📝 {seller.get('description') or '-'}\n"
        f"🖼 {'✅' if seller.get('photo_id') else '❌'}"
    )


# ================= GLOBAL RESET =================

@router.message(F.text == "🔄 Оновити Bot")
async def global_restart(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


# ================= GLOBAL HOME =================

@router.message(F.text.in_(["↩️ На головне меню", "↩️ Головне меню"]))
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

    payload = _start_payload(message)
    try:
        await upsert_telegram_attribution(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            language_code=message.from_user.language_code,
            start_param=payload or None,
        )
    except Exception as e:
        print("ERROR SAVE TELEGRAM ATTRIBUTION:", e)

    if payload.upper() == START_PROMO_CODE:
        existing_activation = await get_promo_activation(
            message.from_user.id,
            START_PROMO_CODE,
        )
        activation = await activate_start_promo(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )

        await message.answer(
            _promo_activation_text(),
            reply_markup=_promo_profile_kb(),
        )

        if not existing_activation:
            await _notify_admins_about_start_promo(
                message.bot,
                message.from_user,
                activation,
            )
        return

    await message.answer(
        "🔁 Головне меню\n\nОбери дію:",
        reply_markup=await main_menu_kb(message.from_user.id),
    )


@router.callback_query(F.data == "promo:fill_profile")
async def promo_fill_profile(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    await create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username
    )
    await log_visit(callback.from_user, role="seller")
    await get_or_create_seller(callback.from_user.id, callback.from_user.username)

    seller = await _get_seller_profile(callback.from_user.id)

    await callback.message.answer(
        "🏪 Режим продавця\nЗаповніть профіль та інформацію про бізнес:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.message.answer(
        _render_seller_profile(seller),
        parse_mode="HTML",
        reply_markup=profile_edit_kb(),
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
