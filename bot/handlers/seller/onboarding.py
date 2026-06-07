import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from bot.config import ADMIN_IDS
from bot.database.repositories.seller_repo import (
    create_or_update_pending_seller_profile,
    get_seller_by_telegram_id,
)
from bot.keyboards.admin_inline import seller_onboarding_review_kb
from bot.keyboards.seller_menu import seller_menu_kb
from bot.states.seller_states import SellerStates

router = Router()

DIRECTIONS = (
    "авто на розборі",
    "магазин запчастин",
    "СТО / послуги",
    "евакуатор",
    "інше",
)


def _phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Використати телефон з Telegram", request_contact=True)],
            [KeyboardButton(text="✍️ Ввести вручну")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _application_start_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Подати заявку продавця")],
            [KeyboardButton(text="💬 Підтримка")],
            [KeyboardButton(text="↩️ Головне меню")],
        ],
        resize_keyboard=True,
    )


def _direction_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=item)] for item in DIRECTIONS],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _clean(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _normalize_phone(value: str | None) -> str:
    return _clean(value).replace(" ", "")


def _seller_application_admin_text(seller) -> str:
    tags = seller.get("specialization_tags") or []
    direction = tags[0] if tags else "—"
    username = f"@{seller['username']}" if seller.get("username") else "—"
    return (
        "🆕 <b>Нова заявка продавця</b>\n\n"
        f"Telegram ID: <code>{seller['telegram_id']}</code>\n"
        f"Username: {html.escape(username)}\n"
        f"Назва: {html.escape(seller.get('shop_name') or '—')}\n"
        f"Імʼя: {html.escape(seller.get('name') or '—')}\n"
        f"Телефон: {html.escape(seller.get('phone') or '—')}\n"
        f"Місто: {html.escape(seller.get('city') or '—')}\n"
        f"Напрям: {html.escape(direction)}"
    )


async def start_seller_onboarding(message: Message, state: FSMContext, *, edit: bool = False) -> None:
    await state.clear()
    await state.update_data(onboarding_edit=edit)
    await state.set_state(SellerStates.onboarding_company)
    await message.answer(
        "🏪 <b>Заявка продавця</b>\n\n"
        "Щоб відкрити доступ до CRM, заповніть коротку анкету.\n\n"
        "Назва компанії / магазину:",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )


async def show_pending_seller_status(message: Message) -> None:
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await message.answer(
            "Спочатку подайте заявку продавця.",
            reply_markup=_application_start_kb(),
        )
        return

    if seller.get("is_verified"):
        await message.answer(
            "✅ Ваш профіль продавця підтверджено. CRM доступна.",
            reply_markup=seller_menu_kb(is_verified=True),
        )
        return

    if not seller.get("shop_name") or not seller.get("phone"):
        await message.answer(
            "📝 <b>Анкету продавця ще не завершено</b>\n\n"
            "Натисніть «Редагувати дані», щоб подати заявку на перевірку.",
            parse_mode="HTML",
            reply_markup=seller_menu_kb(is_verified=False),
        )
        return

    await message.answer(
        "⏳ <b>Статус перевірки: заявка на розгляді</b>\n\n"
        "Заявку продавця прийнято. Після перевірки ви отримаєте доступ до CRM.",
        parse_mode="HTML",
        reply_markup=seller_menu_kb(is_verified=False),
    )


@router.message(F.text.in_(["📝 Подати заявку продавця", "🏪 Стати продавцем", "🏪 Режим продавця", "Стати продавцем", "Режим продавця"]))
async def seller_onboarding_entry_message(message: Message, state: FSMContext):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await start_seller_onboarding(message, state)
        return
    if seller.get("is_verified"):
        await message.answer(
            "✅ Ви вже підтверджений продавець. Відкриваю меню продавця.",
            reply_markup=seller_menu_kb(is_verified=True),
        )
        return
    if not seller.get("shop_name") or not seller.get("phone"):
        await start_seller_onboarding(message, state, edit=True)
        return
    await show_pending_seller_status(message)


@router.message(F.text == "📌 Статус перевірки")
async def seller_verification_status(message: Message):
    await show_pending_seller_status(message)


@router.message(F.text == "✏️ Редагувати дані")
async def edit_pending_seller_data(message: Message, state: FSMContext):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if seller and seller.get("is_verified"):
        await message.answer(
            "Ваш профіль вже підтверджено. Для зміни даних скористайтесь профілем продавця або підтримкою.",
            reply_markup=seller_menu_kb(is_verified=True),
        )
        return
    await start_seller_onboarding(message, state, edit=True)


@router.message(SellerStates.onboarding_company)
async def onboarding_company(message: Message, state: FSMContext):
    value = _clean(message.text)
    if len(value) < 2:
        await message.answer("Вкажіть назву компанії або магазину.")
        return
    await state.update_data(company=value)
    await state.set_state(SellerStates.onboarding_contact_name)
    await message.answer("Імʼя контактної особи:")


@router.message(SellerStates.onboarding_contact_name)
async def onboarding_contact_name(message: Message, state: FSMContext):
    value = _clean(message.text)
    if len(value) < 2:
        await message.answer("Вкажіть імʼя контактної особи.")
        return
    await state.update_data(contact_name=value)
    await state.set_state(SellerStates.onboarding_phone)
    await message.answer(
        "Телефон для звʼязку:\n\n"
        "Можете поділитися телефоном з Telegram або ввести вручну.",
        reply_markup=_phone_kb(),
    )


@router.message(SellerStates.onboarding_phone, F.contact)
async def onboarding_phone_contact(message: Message, state: FSMContext):
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Будь ласка, надішліть власний контакт або введіть телефон вручну.")
        return
    await state.update_data(phone=_normalize_phone(contact.phone_number))
    await state.set_state(SellerStates.onboarding_city)
    await message.answer("Місто:", reply_markup=ReplyKeyboardRemove())


@router.message(SellerStates.onboarding_phone)
async def onboarding_phone_text(message: Message, state: FSMContext):
    if message.text == "✍️ Ввести вручну":
        await message.answer("Введіть телефон у форматі +380...")
        return
    value = _normalize_phone(message.text)
    digits = [ch for ch in value if ch.isdigit()]
    if len(digits) < 9:
        await message.answer("Вкажіть коректний телефон або поділіться контактом з Telegram.")
        return
    await state.update_data(phone=value)
    await state.set_state(SellerStates.onboarding_city)
    await message.answer("Місто:", reply_markup=ReplyKeyboardRemove())


@router.message(SellerStates.onboarding_city)
async def onboarding_city(message: Message, state: FSMContext):
    value = _clean(message.text)
    if len(value) < 2:
        await message.answer("Вкажіть місто.")
        return
    await state.update_data(city=value)
    await state.set_state(SellerStates.onboarding_direction)
    await message.answer("Напрям діяльності:", reply_markup=_direction_kb())


@router.message(SellerStates.onboarding_direction)
async def onboarding_direction(message: Message, state: FSMContext):
    direction = _clean(message.text)
    if direction not in DIRECTIONS:
        await message.answer("Оберіть напрям діяльності з кнопок нижче.", reply_markup=_direction_kb())
        return

    data = await state.get_data()
    seller = await create_or_update_pending_seller_profile(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        shop_name=data["company"],
        contact_name=data["contact_name"],
        phone=data["phone"],
        city=data["city"],
        direction=direction,
    )

    for admin_id in set(ADMIN_IDS):
        try:
            await message.bot.send_message(
                admin_id,
                _seller_application_admin_text(seller),
                parse_mode="HTML",
                reply_markup=seller_onboarding_review_kb(seller["id"]),
            )
        except Exception as exc:
            print("SELLER_ONBOARDING_ADMIN_NOTIFY_ERROR", admin_id, exc)

    await state.clear()
    await message.answer(
        "✅ Заявку продавця прийнято. Після перевірки ви отримаєте доступ до CRM.",
        reply_markup=seller_menu_kb(is_verified=False),
    )
