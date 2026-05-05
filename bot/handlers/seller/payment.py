from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.database.repositories.payment_repo import get_user_transactions

from bot.services.liqpay_service import LiqPayService
from bot.config import (
    LIQPAY_PUBLIC_KEY,
    LIQPAY_PRIVATE_KEY,
    LIQPAY_CALLBACK_URL
)

router = Router()

liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


PACKAGES = {
    "1": {"slots": 1, "amount": 99},
    "5": {"slots": 5, "amount": 199},
    "10": {"slots": 10, "amount": 299},
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
            f"🔹 {package['slots']} авто — {package['amount']} грн\n\n"
            f"Натисніть кнопку нижче для оплати:",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print("ERROR BUY PACKAGE:", e)
        await message.answer("⚠️ Сталась помилка при створенні платежу")


# ================= CREATE SITE PAYMENT =================

async def _create_site_payment(message: Message, telegram_id: int):
    try:
        seller = await get_seller_by_telegram_id(telegram_id)

        if not seller:
            await message.answer("❌ Помилка: продавець не знайдений. Напишіть /start")
            return

        seller_id = seller["id"]

        # ❗ FIX: description прибрано
        payment = await liqpay.create_payment(
            amount=499,
            server_url=LIQPAY_CALLBACK_URL,
            seller_id=seller_id,
            product="site"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="💳 Оплатити сайт", url=payment["url"])

        await message.answer(
            "🌐 <b>Створення сайту</b>\n\n"
            "🔹 Власний сайт\n"
            "🔹 Список авто\n"
            "🔹 Прийом заявок\n\n"
            "💰 499 грн\n\n"
            "Після оплати сайт створиться автоматично",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )

    except Exception as e:
        print("ERROR SITE PAYMENT:", e)
        await message.answer("⚠️ Помилка створення платежу")


# ================= MENU =================

@router.message(F.text == "💳 Пакети послуг")
async def show_packages(message: Message):
    kb = InlineKeyboardBuilder()

    kb.button(text="🚗 1 авто — 99 грн", callback_data="package:1")
    kb.button(text="🚗 5 авто — 199 грн", callback_data="package:5")
    kb.button(text="🚗 10 авто — 299 грн", callback_data="package:10")
    kb.button(text="🌐 Сайт — 499 грн", callback_data="buy:site")
    kb.button(text="📊 Історія транзакцій", callback_data="seller:transactions")

    kb.adjust(1)

    await message.answer(
        "💳 <b>Пакети послуг</b>\n\n"
        "Оберіть:",
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )


# ================= CALLBACKS =================

@router.callback_query(F.data.startswith("package:"))
async def buy_package_callback(callback: CallbackQuery):
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
    await _create_site_payment(
        callback.message,
        callback.from_user.id
    )
    await callback.answer()


# ================= TRANSACTIONS =================

@router.callback_query(F.data == "seller:transactions")
async def show_transactions(callback: CallbackQuery):
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
            text += f"Зараховано {t.get('slots', 0)} місце(ць)\n"

        elif t.get("product") == "site" and t["status"] == "success":
            text += "🌐 Сайт створено\n"

        text += f"{t['created_at']}\n\n"

    await callback.message.answer(text)
