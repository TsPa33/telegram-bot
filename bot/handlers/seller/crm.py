import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import LIQPAY_CALLBACK_URL, LIQPAY_PRIVATE_KEY, LIQPAY_PUBLIC_KEY, SELLER_CRM_BASE_URL
from bot.database.repositories.seller_crm_repo import (
    create_crm_subscription,
    get_active_crm_subscription,
    get_crm_account_by_seller,
    get_successful_crm_payment_without_subscription,
    seller_has_active_crm,
    upsert_crm_account,
)
from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.keyboards.seller_menu import seller_menu_kb
from bot.services.liqpay_service import LiqPayService
from bot.services.seller_crm import (
    SELLER_CRM_MONTHLY_PRICE_UAH,
    SELLER_CRM_PRODUCT,
    SELLER_CRM_SUBSCRIPTION_DAYS,
    hash_crm_password,
    validate_crm_password,
    validate_crm_slug,
)
from bot.states.seller_states import SellerCrmStates

logger = logging.getLogger(__name__)

router = Router()
liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


def _crm_url(slug: str | None = None) -> str:
    base = (SELLER_CRM_BASE_URL or "https://crm.carpot.com.ua").rstrip("/")
    return f"{base}/crm/seller/{slug}" if slug else base


def _landing_kb(has_active_subscription: bool = False, account_slug: str | None = None):
    kb = InlineKeyboardBuilder()
    kb.button(text="👀 Переглянути демо", url=f"{_crm_url()}/crm/seller/demo")
    if account_slug:
        kb.button(text="🚀 Відкрити CRM", url=_crm_url(account_slug))
    elif has_active_subscription:
        kb.button(text="🧩 Створити CRM акаунт", callback_data="seller_crm:setup")
    else:
        kb.button(text=f"💳 Підключити CRM — {SELLER_CRM_MONTHLY_PRICE_UAH} грн/міс", callback_data="seller_crm:buy")
    kb.button(text="⬅️ Назад", callback_data="seller_crm:back")
    kb.adjust(1)
    return kb.as_markup()


def _landing_text(has_active_subscription: bool = False, account_slug: str | None = None) -> str:
    status = "✅ CRM підписка активна" if has_active_subscription else "🔒 Доступ відкривається після оплати"
    if account_slug:
        status = f"🚀 Ваш CRM кабінет: {_crm_url(account_slug)}"

    return (
        "💼 <b>Професійна CRM CarPot</b>\n\n"
        "Преміальний операційний dashboard для авто-бізнесу: заявки, клієнти, "
        "аналітика, сайт-статистика та контроль конверсій в одному місці.\n\n"
        "<b>Що всередині:</b>\n"
        "▫️ CRM dashboard preview з ключовими KPI\n"
        "▫️ Заявки з Telegram та сайту\n"
        "▫️ Аналітика переглядів, CTA та джерел реклами\n"
        "▫️ Website statistics і conversion tracking\n"
        "▫️ Авто / послуги / активні оголошення\n"
        "▫️ Управління підпискою CRM\n\n"
        f"<b>Вартість:</b> {SELLER_CRM_MONTHLY_PRICE_UAH} грн/міс\n"
        f"<b>Статус:</b> {status}"
    )


async def _seller_context(telegram_id: int):
    seller = await get_seller_by_telegram_id(telegram_id)
    if not seller:
        return None, None, False
    account = await get_crm_account_by_seller(seller["id"])
    active = await seller_has_active_crm(seller["id"])
    return seller, account, active


@router.message(F.text == "💼 Професійна CRM")
async def seller_crm_landing(message: Message):
    seller, account, active = await _seller_context(message.from_user.id)
    if not seller:
        await message.answer("❌ Продавця не знайдено. Натисніть /start і завершіть реєстрацію.")
        return

    await message.answer(
        _landing_text(active, account["crm_slug"] if account else None),
        parse_mode="HTML",
        reply_markup=_landing_kb(active, account["crm_slug"] if account else None),
    )


@router.callback_query(F.data == "seller_crm:back")
async def seller_crm_back(callback: CallbackQuery):
    seller = await get_seller_by_telegram_id(callback.from_user.id)
    await callback.message.answer(
        "Меню продавця",
        reply_markup=seller_menu_kb(is_verified=seller.get("is_verified", False) if seller else False),
    )
    await callback.answer()


@router.callback_query(F.data == "seller_crm:buy")
async def seller_crm_buy(callback: CallbackQuery):
    logger.info("CRM_PAYMENT_BUTTON_CLICKED telegram_id=%s", callback.from_user.id)

    try:
        seller = await get_seller_by_telegram_id(callback.from_user.id)
        if not seller:
            logger.warning("CRM_PAYMENT_SELLER_NOT_FOUND telegram_id=%s", callback.from_user.id)
            await callback.answer("Продавця не знайдено", show_alert=True)
            return

        logger.info("CRM_PAYMENT_SELLER_RESOLVED seller_id=%s", seller["id"])

        payment = await liqpay.create_payment(
            amount=SELLER_CRM_MONTHLY_PRICE_UAH,
            server_url=LIQPAY_CALLBACK_URL,
            seller_id=seller["id"],
            product=SELLER_CRM_PRODUCT,
        )
    except Exception:
        logger.exception(
            "CRM_PAYMENT_CREATE_FAILED telegram_id=%s",
            callback.from_user.id,
        )
        await callback.answer("Не вдалося створити оплату CRM. Спробуйте ще раз.", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Оплатити CRM", url=payment["url"])
    kb.button(text="✅ Я оплатив — створити CRM", callback_data="seller_crm:setup")
    kb.adjust(1)

    await callback.message.answer(
        "💼 <b>Підключення Професійної CRM</b>\n\n"
        f"Сума: <b>{SELLER_CRM_MONTHLY_PRICE_UAH} грн / місяць</b>\n"
        "Після успішної оплати натисніть «Створити CRM», щоб обрати адресу та пароль.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "seller_crm:setup")
async def seller_crm_setup(callback: CallbackQuery, state: FSMContext):
    seller = await get_seller_by_telegram_id(callback.from_user.id)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    subscription = await get_active_crm_subscription(seller["id"])
    if not subscription:
        successful_payment = await get_successful_crm_payment_without_subscription(
            seller["id"],
            SELLER_CRM_PRODUCT,
        )
        if successful_payment:
            try:
                subscription = await create_crm_subscription(
                    seller["id"],
                    successful_payment["id"],
                    days=SELLER_CRM_SUBSCRIPTION_DAYS,
                )
            except Exception:
                logger.exception(
                    "CRM_SUBSCRIPTION_RECOVERY_FAILED seller_id=%s payment_id=%s",
                    seller["id"],
                    successful_payment["id"],
                )
                await callback.answer(
                    "Оплату знайдено, але CRM ще не активувалась. Напишіть у підтримку.",
                    show_alert=True,
                )
                return

    if not subscription:
        await callback.answer("CRM активується після успішної оплати", show_alert=True)
        return

    existing = await get_crm_account_by_seller(seller["id"])
    if existing:
        kb = InlineKeyboardBuilder()
        kb.button(text="🚀 Відкрити CRM", url=_crm_url(existing["crm_slug"]))
        await callback.message.answer(
            "✅ CRM акаунт вже створено\n\n"
            f"🌐 CRM: {_crm_url(existing['crm_slug'])}\n"
            f"👤 Логін: {seller['telegram_id']}",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    await state.set_state(SellerCrmStates.crm_slug)
    await callback.message.answer(
        "🧩 <b>Створення CRM акаунта</b>\n\n"
        "Введіть коротку адресу для CRM латиницею.\n"
        "Приклад: <code>sto-kyiv</code>\n\n"
        f"Ваш кабінет буде доступний як: <code>{_crm_url('sto-kyiv')}</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SellerCrmStates.crm_slug)
async def seller_crm_slug_entered(message: Message, state: FSMContext):
    valid, result = validate_crm_slug(message.text)
    if not valid:
        await message.answer(f"❌ {result}\n\nСпробуйте ще раз, наприклад: <code>sto-kyiv</code>", parse_mode="HTML")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller or not await get_active_crm_subscription(seller["id"]):
        await state.clear()
        await message.answer("🔒 Активної CRM підписки не знайдено. Спочатку оплатіть CRM.")
        return

    await state.update_data(crm_slug=result)
    await state.set_state(SellerCrmStates.crm_password)
    await message.answer(
        "🔒 Створіть пароль для CRM.\n\n"
        "Вимоги: мінімум 8 символів, літери та цифри. Пароль буде збережений тільки у вигляді хешу.",
    )


@router.message(SellerCrmStates.crm_password)
async def seller_crm_password_entered(message: Message, state: FSMContext):
    valid, error = validate_crm_password(message.text)
    if not valid:
        await message.answer(f"❌ {error}\n\nВведіть інший пароль:")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller or not await get_active_crm_subscription(seller["id"]):
        await state.clear()
        await message.answer("🔒 Активної CRM підписки не знайдено. Спочатку оплатіть CRM.")
        return

    data = await state.get_data()
    slug = data["crm_slug"]

    try:
        account = await upsert_crm_account(seller["id"], slug, hash_crm_password(message.text))
    except Exception as exc:
        print("SELLER CRM ACCOUNT ERROR:", exc)
        await message.answer("❌ Така CRM адреса вже зайнята. Введіть іншу адресу:")
        await state.set_state(SellerCrmStates.crm_slug)
        return

    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Відкрити CRM", url=_crm_url(account["crm_slug"]))

    await message.answer(
        "✅ <b>CRM акаунт створено</b>\n\n"
        f"🌐 CRM:\n{_crm_url(account['crm_slug'])}\n\n"
        f"👤 Логін:\n{seller['telegram_id']}\n\n"
        "🔒 Пароль:\nстворений вами пароль (ми не зберігаємо його у відкритому вигляді)",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
