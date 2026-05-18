import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import LIQPAY_CALLBACK_URL, LIQPAY_PRIVATE_KEY, LIQPAY_PUBLIC_KEY, SELLER_CRM_BASE_URL
from bot.database.repositories.seller_crm_repo import (
    enable_seller_crm,
    get_crm_account_by_seller,
    upsert_crm_account,
)
from bot.database.repositories.seller_repo import get_or_create_seller, get_seller_by_telegram_id
from bot.keyboards.seller_menu import seller_menu_kb
from bot.services.liqpay_service import LiqPayService
from bot.services.seller_crm import (
    SELLER_CRM_MONTHLY_PRICE_UAH,
    SELLER_CRM_PRODUCT,
    create_crm_password_reset_token,
    ensure_crm_credentials,
    hash_crm_password,
    validate_crm_password,
    validate_crm_slug,
)
from bot.states.seller_states import SellerCrmStates

logger = logging.getLogger(__name__)

router = Router()
liqpay = LiqPayService(LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY)


def _crm_url(slug: str | None = None) -> str:
    base = (SELLER_CRM_BASE_URL or "https://carpot.com.ua").rstrip("/")
    return f"{base}/crm/seller/{slug}" if slug else base


def _crm_setup_password_url(slug: str) -> str:
    return f"{_crm_url()}/crm/seller/setup-password?slug={slug}"


def _crm_reset_password_url(account) -> str:
    token = create_crm_password_reset_token(dict(account))
    return f"{_crm_url()}/crm/seller/reset-password?slug={account['crm_slug']}&token={token}"


def _landing_kb(account, setup_required: bool = False):
    account_slug = account["crm_slug"]
    kb = InlineKeyboardBuilder()
    if setup_required:
        kb.button(text="🔐 Створити пароль CRM", url=_crm_setup_password_url(account_slug))
    else:
        kb.button(text="🚀 Відкрити CRM", url=_crm_url(account_slug))
        kb.button(text="🛟 Скинути пароль CRM", url=_crm_reset_password_url(account))
    kb.button(text="👀 Переглянути демо", url=f"{_crm_url()}/crm/seller/demo")
    kb.button(text="⬅️ Назад", callback_data="seller_crm:back")
    kb.adjust(1)
    return kb.as_markup()


def _crm_login(seller) -> str:
    return str(seller["telegram_id"])


def _landing_text(account_slug: str, login: str, setup_required: bool = False) -> str:
    if setup_required:
        return (
            "🔐 <b>CRM акаунт готовий до першого входу</b>\n\n"
            f"CRM:\n{_crm_url(account_slug)}\n\n"
            f"Логін:\n<code>{login}</code>\n\n"
            "Щоб увійти, створіть пароль на захищеній сторінці першого налаштування."
        )

    return (
        "🌐 <b>CRM готовий</b>\n\n"
        f"URL:\n{_crm_url(account_slug)}\n\n"
        f"Логін:\n<code>{login}</code>"
    )


async def _ensure_seller_crm(telegram_id: int, username: str | None):
    seller = await get_or_create_seller(telegram_id, username)
    account, setup_required = await ensure_crm_credentials(dict(seller))
    logger.info("CRM_ACCESS_READY seller_id=%s slug=%s", seller["id"], account["crm_slug"])
    return seller, account, setup_required


@router.message(F.text == "🧾 Відкрити CRM")
async def seller_crm_landing(message: Message):
    try:
        _seller, account, setup_required = await _ensure_seller_crm(
            message.from_user.id,
            message.from_user.username,
        )
    except Exception:
        logger.exception("CRM_AUTO_PROVISION_FAILED telegram_id=%s", message.from_user.id)
        await message.answer("❌ Не вдалося підготувати CRM. Спробуйте ще раз або напишіть у підтримку.")
        return

    await message.answer(
        _landing_text(account["crm_slug"], _crm_login(_seller), setup_required),
        parse_mode="HTML",
        reply_markup=_landing_kb(account, setup_required),
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
        "💼 <b>Додатковий CRM пакет</b>\n\n"
        f"Сума: <b>{SELLER_CRM_MONTHLY_PRICE_UAH} грн / місяць</b>\n"
        "Базовий CRM вже безкоштовний. Цей платіж залишено для сумісності з майбутніми платними можливостями.",
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

    await enable_seller_crm(seller["id"])

    existing = await get_crm_account_by_seller(seller["id"])
    if existing:
        account, setup_required = await ensure_crm_credentials(dict(seller))
        await callback.message.answer(
            _landing_text(account["crm_slug"], _crm_login(seller), setup_required),
            parse_mode="HTML",
            reply_markup=_landing_kb(account, setup_required),
        )
        await callback.answer()
        return

    await state.set_state(SellerCrmStates.crm_slug)
    await callback.message.answer(
        "🧩 <b>Налаштування CRM акаунта</b>\n\n"
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
    if not seller:
        await state.clear()
        await message.answer("❌ Продавця не знайдено. Натисніть /start і завершіть реєстрацію.")
        return
    await enable_seller_crm(seller["id"])

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
    if not seller:
        await state.clear()
        await message.answer("❌ Продавця не знайдено. Натисніть /start і завершіть реєстрацію.")
        return
    await enable_seller_crm(seller["id"])

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
        "✅ <b>CRM акаунт готовий</b>\n\n"
        f"🌐 CRM:\n{_crm_url(account['crm_slug'])}\n\n"
        f"👤 Логін:\n{seller['telegram_id']}\n\n"
        "🔒 Пароль:\nстворений вами пароль (ми не зберігаємо його у відкритому вигляді)",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
