from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.database.repositories.payment_repo import get_user_transactions

from bot.services.liqpay_service import LiqPayService
from bot.services.site_packages import (
    SITE_PACKAGES,
    format_site_package_title,
    format_site_packages_text,
    get_or_create_package_seller,
    get_site_package,
    get_site_package_amount,
    notify_admins_about_site_package,
)
from bot.keyboards.admin_inline import site_packages_kb
from bot.services.seller_access import get_verified_seller_or_warn
from bot.config import (
    LIQPAY_PUBLIC_KEY,
    LIQPAY_PRIVATE_KEY,
    LIQPAY_CALLBACK_URL
)

router = Router()

liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


PACKAGES = {
    "1": {"cars": 1, "amount": 99, "title": "1 авто", "subtitle": "Підійде для старту."},
    "5": {"cars": 5, "amount": 199, "title": "5 авто", "subtitle": "Для активної розборки."},
    "10": {"cars": 10, "amount": 299, "title": "10 авто", "subtitle": "Максимальний пакет."},
}


# ================= CREATE GARAGE PAYMENT =================

async def _create_package_payment(message: Message, package_key: str, telegram_id: int):
    try:
        package = PACKAGES[package_key]

        seller = await get_seller_by_telegram_id(telegram_id)

        if not seller:
            await message.answer("❌ Помилка: продавець не знайдений. Напишіть /start")
            return

        seller_id = seller["id"]

        # ❗ FIX: description прибрано
        payment = await liqpay.create_payment(
            amount=package["amount"],
            server_url=LIQPAY_CALLBACK_URL,
            seller_id=seller_id,
            product="garage"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатити", url=payment["url"])

        await message.answer(
            f"💳 <b>Оплата</b>\n\n"
            f"🔹 {package['title']} — {package['amount']} грн / місяць\n"
            f"{package['subtitle']}\n\n"
            "Після активації додайте авто на розбір — CarPot створить запчастини та почне приймати заявки.",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print("ERROR BUY PACKAGE:", e)
        await message.answer("⚠️ Сталась помилка при створенні платежу")


# ================= CREATE SITE PAYMENT / LEAD =================

async def _create_site_payment(message: Message, telegram_id: int, package_key: str = "standard", user=None):
    try:
        package = get_site_package(package_key)

        if not package:
            await message.answer("❌ Невідомий пакет сайту")
            return

        user = user or getattr(message, "from_user", None)

        if not user:
            await message.answer("❌ Не вдалося визначити користувача. Напишіть /start")
            return

        seller = await get_or_create_package_seller(user)

        if not seller:
            await message.answer("❌ Помилка: продавець не знайдений. Напишіть /start")
            return

        seller_id = seller["id"]
        amount = get_site_package_amount(package_key)

        await notify_admins_about_site_package(message.bot, user, package_key)

        if package.get("payment_product") == "site" and amount:
            payment = await liqpay.create_payment(
                amount=amount,
                server_url=LIQPAY_CALLBACK_URL,
                seller_id=seller_id,
                product=package["payment_product"]
            )

            kb = InlineKeyboardBuilder()
            kb.button(text="💳 Оплатити сайт", url=payment["url"])

            await message.answer(
                f"🌐 <b>{format_site_package_title(package_key)}</b>\n\n"
                f"{package['description']}\n\n"
                "Після оплати сайт створиться автоматично.\n"
                "Адміністратор також отримав заявку.",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
            return

        await message.answer(
            f"✅ <b>Заявку прийнято</b>\n\n"
            f"Пакет: {format_site_package_title(package_key)}\n\n"
            "Адміністратор звʼяжеться з вами для уточнення деталей.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("ERROR SITE PAYMENT:", e)
        await message.answer("⚠️ Помилка створення заявки на сайт")



async def _callback_verified_or_warn(callback: CallbackQuery) -> bool:
    seller = await get_seller_by_telegram_id(callback.from_user.id)
    if seller and seller.get("is_verified"):
        return True
    await callback.message.answer(
        "⏳ Профіль продавця ще не підтверджено. Пакети послуг стануть доступні після перевірки.",
    )
    await callback.answer()
    return False

# ================= MENU =================

@router.message(F.text == "💳 Пакети послуг")
async def show_packages(message: Message):
    if not await get_verified_seller_or_warn(message):
        return

    kb = InlineKeyboardBuilder()

    kb.button(text="🚗 1 авто — 99 грн / місяць", callback_data="package:1")
    kb.button(text="🚗 5 авто — 199 грн / місяць", callback_data="package:5")
    kb.button(text="🚗 10 авто — 299 грн / місяць", callback_data="package:10")
    kb.button(text="🌐 Власний сайт", callback_data="site:packages")
    kb.button(text="📊 Історія транзакцій", callback_data="seller:transactions")

    kb.adjust(1)

    text = """💳 <b>Пакети CarPot</b>

Оберіть, як хочете отримувати заявки:

<b>A. Авторозборка через CarPot marketplace</b>
Додавайте авто на розбір. CarPot автоматично створює 130+ запчастин, публікує їх у каталозі та надсилає заявки в Telegram/CRM.

<b>1 авто — 99 грн / місяць</b>
Підійде для старту.
✓ 1 авто на розборі
✓ CRM
✓ Каталог CarPot
✓ Telegram сповіщення
✓ VIN заявки

<b>5 авто — 199 грн / місяць</b>
Для активної розборки.
✓ 5 авто на розборі
✓ CRM
✓ Каталог CarPot
✓ Telegram сповіщення
✓ VIN заявки

<b>10 авто — 299 грн / місяць</b>
Максимальний пакет.
✓ 10 авто на розборі
✓ CRM
✓ Каталог CarPot
✓ Telegram сповіщення
✓ VIN заявки

<b>B. Власний сайт</b>
Створіть сайт з каталогом або послугами та отримуйте заявки напряму з сайту додатково до CarPot."""

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )


# ================= CALLBACKS =================

@router.callback_query(F.data.startswith("package:"))
async def buy_package_callback(callback: CallbackQuery):
    if not await _callback_verified_or_warn(callback):
        return

    package_key = callback.data.split(":")[1]

    if package_key not in PACKAGES:
        await callback.answer("Невідомий пакет", show_alert=True)
        return

    await _create_package_payment(
        callback.message,
        package_key,
        callback.from_user.id
    )

    await callback.answer()


@router.callback_query(F.data == "buy:site")
async def buy_site(callback: CallbackQuery):
    if not await _callback_verified_or_warn(callback):
        return

    await _create_site_payment(
        callback.message,
        callback.from_user.id,
        "standard",
        user=callback.from_user
    )
    await callback.answer()


@router.callback_query(F.data == "site:packages")
async def site_packages(callback: CallbackQuery):
    if not await _callback_verified_or_warn(callback):
        return

    await callback.message.answer(
        format_site_packages_text(),
        parse_mode="HTML",
        reply_markup=site_packages_kb(back_callback="demo:sites"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:package:"))
async def site_package_selected(callback: CallbackQuery):
    if not await _callback_verified_or_warn(callback):
        return

    package_key = callback.data.split(":")[-1]

    if package_key not in SITE_PACKAGES:
        await callback.answer("Невідомий пакет сайту", show_alert=True)
        return

    await _create_site_payment(
        callback.message,
        callback.from_user.id,
        package_key,
        user=callback.from_user
    )
    await callback.answer("Заявку передано адміністратору")


# ================= TRANSACTIONS =================

@router.callback_query(F.data == "seller:transactions")
async def show_transactions(callback: CallbackQuery):
    if not await _callback_verified_or_warn(callback):
        return

    await callback.answer()

    transactions = await get_user_transactions(callback.from_user.id)

    if not transactions:
        await callback.message.answer("📭 Транзакцій ще немає")
        return

    text = ""

    for t in transactions:
        status = "УСПІШНО" if t["status"] == "success" else "ВІДМОВЛЕНО"
        icon = "✅" if t["status"] == "success" else "⚠️"

        text += f"{icon} Оплата {t['amount']} грн\n"
        text += f"({status})\n"

        if t.get("product") == "garage":
            text += f"Зараховано авто на розборі: {t.get('slots', 0)}\n"

        elif t.get("product") == "site" and t["status"] == "success":
            text += "🌐 Сайт створено\n"

        elif t.get("product") == "seller_crm" and t["status"] == "success":
            text += "💼 CRM активовано на 30 днів\n"

        text += f"{t['created_at']}\n\n"

    await callback.message.answer(text)
