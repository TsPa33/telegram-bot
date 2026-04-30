from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.database.repositories.service_repo import (
    create_service,
    delete_service,
    get_services_by_seller,
    update_service_field,
)
from bot.database.repositories.seller_repo import (
    get_or_create_seller,
    get_seller_by_telegram_id,
)
from bot.keyboards.seller_menu import seller_menu_kb
from bot.states.service_states import ServiceStates
from .verification import check_verified

router = Router()

ADD_SERVICE_BACK = KeyboardButton(text="⬅️ Назад у профіль")
SKIP_WEBSITE = KeyboardButton(text="⚠️ Пропустити")


# ================= KEYBOARDS =================

def services_list_kb(services):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=s["title"], callback_data=f"service:{s['id']}")]
            for s in services
        ]
    )


def actions_kb(service_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"service_edit:{service_id}"),
                InlineKeyboardButton(text="🗑 Видалити", callback_data=f"service_delete:{service_id}"),
            ]
        ]
    )


def edit_kb(service_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"edit_photo:{service_id}")],
            [InlineKeyboardButton(text="✏️ Назва", callback_data=f"edit_title:{service_id}")],
            [InlineKeyboardButton(text="📝 Опис", callback_data=f"edit_desc:{service_id}")],
            [InlineKeyboardButton(text="💰 Ціна", callback_data=f"edit_price:{service_id}")],
        ]
    )


# ================= ADD =================

@router.message(F.text == "➕ Додати послугу")
async def add_start(message: Message, state: FSMContext):
    await state.clear()

    if not await check_verified(message, state):
        return

    await state.set_state(ServiceStates.title)
    await state.update_data(flow="add")

    await message.answer("Введіть назву послуги")


@router.message(ServiceStates.title)
async def add_title(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "add":
        return

    await state.update_data(title=message.text)
    await state.set_state(ServiceStates.description)
    await message.answer("Введіть опис")


@router.message(ServiceStates.description)
async def add_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "add":
        return

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)

    await create_service(
        seller_id=seller["id"],
        category="default",
        title=data["title"],
        city="",
        address="",
        description=message.text,
        website=None,
        photo_id=None,
    )

    await state.clear()

    await message.answer("✅ Послугу створено", reply_markup=seller_menu_kb(seller.get("is_verified")))


# ================= LIST =================

@router.message(F.text == "📋 Мої послуги")
async def my_services(message: Message, state: FSMContext):
    await state.clear()

    seller = await get_seller_by_telegram_id(message.from_user.id)
    services = await get_services_by_seller(seller["id"])

    if not services:
        await message.answer("У вас немає послуг")
        return

    await message.answer("Ваші послуги:", reply_markup=services_list_kb(services))


# ================= OPEN =================

@router.callback_query(F.data.startswith("service:"))
async def open_service(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])

    seller = await get_seller_by_telegram_id(callback.from_user.id)
    services = await get_services_by_seller(seller["id"])

    service = next((s for s in services if s["id"] == service_id), None)

    if not service:
        return

    text = f"{service['title']}\n{service.get('description') or ''}"

    await callback.message.answer(text, reply_markup=actions_kb(service_id))


# ================= DELETE =================

@router.callback_query(F.data.startswith("service_delete:"))
async def delete_handler(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])

    seller = await get_seller_by_telegram_id(callback.from_user.id)
    services = await get_services_by_seller(seller["id"])

    if not any(s["id"] == service_id for s in services):
        return

    await delete_service(service_id)

    await callback.message.answer("🗑 Видалено")


# ================= EDIT =================

@router.callback_query(F.data.startswith("service_edit:"))
async def edit_menu(callback: CallbackQuery):
    await callback.answer()

    service_id = int(callback.data.split(":")[1])

    await callback.message.answer("Редагування:", reply_markup=edit_kb(service_id))


@router.callback_query(F.data.startswith("edit_title:"))
async def edit_title(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split(":")[1])

    await state.set_state(ServiceStates.edit_value)
    await state.update_data(field="title", service_id=service_id)

    await callback.message.answer("Нова назва:")


@router.callback_query(F.data.startswith("edit_desc:"))
async def edit_desc(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split(":")[1])

    await state.set_state(ServiceStates.edit_value)
    await state.update_data(field="description", service_id=service_id)

    await callback.message.answer("Новий опис:")


@router.callback_query(F.data.startswith("edit_price:"))
async def edit_price(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split(":")[1])

    await state.set_state(ServiceStates.edit_value)
    await state.update_data(field="price", service_id=service_id)

    await callback.message.answer("Введіть ціну:")


@router.callback_query(F.data.startswith("edit_photo:"))
async def edit_photo(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.split(":")[1])

    await state.set_state(ServiceStates.photo)
    await state.update_data(field="photo_id", service_id=service_id)

    await callback.message.answer("Надішліть фото")


@router.message(ServiceStates.photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    data = await state.get_data()

    await update_service_field(
        data["service_id"],
        "photo_id",
        message.photo[-1].file_id
    )

    await state.clear()
    await message.answer("✅ Фото оновлено")


@router.message(ServiceStates.edit_value)
async def save_edit(message: Message, state: FSMContext):
    data = await state.get_data()

    field = data["field"]
    value = message.text

    if field == "price":
        try:
            value = int(value)
        except:
            await message.answer("Введіть число")
            return

    await update_service_field(
        data["service_id"],
        field,
        value
    )

    await state.clear()
    await message.answer("✅ Оновлено")
