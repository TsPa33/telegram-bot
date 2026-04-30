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
    delete_service_by_seller,
    get_service_by_id,
    get_services_by_seller,
    update_service,
)
from bot.database.repositories.seller_repo import get_or_create_seller, get_seller_by_telegram_id
from bot.keyboards.seller_menu import seller_menu_kb
from bot.states.service_states import ServiceStates
from .verification import check_verified

router = Router()

SERVICE_CATEGORIES = ["СТО", "Детейлінг", "Евакуатор", "Шиномонтаж", "Автоелектрик"]

ADD_SERVICE_BACK = KeyboardButton(text="⬅️ Назад у профіль")
SKIP_WEBSITE = KeyboardButton(text="⚠️ Пропустити")


def service_categories_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[ADD_SERVICE_BACK], *[[KeyboardButton(text=cat)] for cat in SERVICE_CATEGORIES]],
        resize_keyboard=True,
    )


def skip_kb():
    return ReplyKeyboardMarkup(keyboard=[[SKIP_WEBSITE]], resize_keyboard=True)


def services_list_kb(services):
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=s["title"], callback_data=f"service:{s['id']}")] for s in services]
    )


def actions_kb(service_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"service_edit:{service_id}"),
            InlineKeyboardButton(text="🗑 Видалити", callback_data=f"service_delete:{service_id}"),
        ]]
    )


def edit_menu_kb(service_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🖼 Змінити фото", callback_data=f"service_edit_field:{service_id}:photo")],
            [InlineKeyboardButton(text="✏️ Редагувати назву", callback_data=f"service_edit_field:{service_id}:title")],
            [InlineKeyboardButton(text="📝 Редагувати опис", callback_data=f"service_edit_field:{service_id}:description")],
            [InlineKeyboardButton(text="💵 Додати/Редагувати ціну", callback_data=f"service_edit_field:{service_id}:price")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="service:list")],
        ]
    )


@router.message(F.text == "➕ Додати послугу")
async def start_add(message: Message, state: FSMContext):
    await state.clear()
    if not await check_verified(message, state):
        return
    await state.set_state(ServiceStates.category)
    await state.update_data(flow="seller_add_service")
    await message.answer("Оберіть категорію:", reply_markup=service_categories_kb())


@router.message(ServiceStates.category)
async def set_category(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_add_service":
        return

    if message.text == "⬅️ Назад у профіль":
        await state.clear()
        seller = await get_or_create_seller(message.from_user.id, message.from_user.username)
        await message.answer("Меню", reply_markup=seller_menu_kb(seller.get("is_verified")))
        return

    if message.text not in SERVICE_CATEGORIES:
        await message.answer("Оберіть категорію з кнопок")
        return

    await state.update_data(category=message.text)
    await state.set_state(ServiceStates.photo)
    await message.answer("Надішліть фото")


@router.message(ServiceStates.photo, F.photo)
async def set_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(ServiceStates.title)
    await message.answer("Назва")


@router.message(ServiceStates.title)
async def set_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(ServiceStates.city)
    await message.answer("Місто")


@router.message(ServiceStates.city)
async def set_city(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_add_service":
        return
    await state.update_data(city=message.text)
    await state.set_state(ServiceStates.address)
    await message.answer("Адреса")


@router.message(ServiceStates.address)
async def set_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(ServiceStates.description)
    await message.answer("Опис")


@router.message(ServiceStates.description)
async def set_description(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") == "seller_service_edit" and data.get("edit_field") == "description":
        ok = await update_service(data["service_id"], "description", message.text)
        await state.clear()
        await message.answer("✅ Опис оновлено" if ok else "❌ Не вдалося оновити")
        return

    await state.update_data(description=message.text)
    await state.set_state(ServiceStates.website)
    await message.answer("Сайт або пропустити", reply_markup=skip_kb())


@router.message(ServiceStates.website)
async def set_website(message: Message, state: FSMContext):
    data = await state.get_data()
    website = None if message.text == "⚠️ Пропустити" else message.text

    seller = await get_or_create_seller(message.from_user.id, message.from_user.username)
    await create_service(
        seller_id=seller["id"],
        category=data["category"],
        title=data["title"],
        city=data["city"],
        address=data["address"],
        description=data.get("description"),
        website=website,
        photo_id=data.get("photo_id"),
    )

    await state.clear()
    await message.answer("✅ Послугу додано", reply_markup=seller_menu_kb(seller.get("is_verified")))


@router.message(F.text == "📋 Мої послуги")
@router.callback_query(F.data == "service:list")
async def my_services(event, state: FSMContext):
    await state.clear()
    user_id = event.from_user.id
    seller = await get_seller_by_telegram_id(user_id)
    if not seller:
        target = event.message if isinstance(event, CallbackQuery) else event
        await target.answer("❌ Помилка продавця")
        return

    services = await get_services_by_seller(seller["id"])
    target = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()

    if not services:
        await target.answer("У вас немає послуг")
        return

    await target.answer("Ваші послуги:", reply_markup=services_list_kb(services))


@router.callback_query(F.data.startswith("service:"))
async def open_service(callback: CallbackQuery):
    await callback.answer()
    service_id = int(callback.data.split(":")[1])
    service = await get_service_by_id(service_id)
    if not service:
        await callback.message.answer("❌ Не знайдено")
        return
    text = f"🔧 {service['title']}\n📍 {service['city']}\n📌 {service['address']}"
    await callback.message.answer(text, reply_markup=actions_kb(service_id))


@router.callback_query(F.data.startswith("service_edit:"))
async def service_edit_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    service_id = int(callback.data.split(":")[1])
    await callback.message.answer("Оберіть, що редагувати:", reply_markup=edit_menu_kb(service_id))


@router.callback_query(F.data.startswith("service_edit_field:"))
async def service_edit_field(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    _, _, service_id, field = callback.data.split(":")
    await state.set_state(ServiceStates.edit_value)
    await state.update_data(flow="seller_service_edit", service_id=int(service_id), edit_field=field)

    prompts = {
        "photo": "Надішліть нове фото послуги",
        "title": "Введіть нову назву",
        "description": "Введіть новий опис",
        "price": "Введіть ціну (буде збережена в описі)",
    }
    await callback.message.answer(prompts.get(field, "Введіть нове значення"))


@router.message(ServiceStates.edit_value, F.photo)
async def edit_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_service_edit" or data.get("edit_field") != "photo":
        return
    ok = await update_service(data["service_id"], "photo_id", message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ Фото оновлено" if ok else "❌ Не вдалося оновити")


@router.message(ServiceStates.edit_value)
async def edit_text_fields(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("flow") != "seller_service_edit":
        return

    field = data.get("edit_field")
    if field == "title":
        ok = await update_service(data["service_id"], "title", message.text)
    elif field == "description":
        ok = await update_service(data["service_id"], "description", message.text)
    elif field == "price":
        service = await get_service_by_id(data["service_id"])
        base = (service.get("description") or "").split("\n\n💵 Ціна:")[0] if service else ""
        value = f"{base}\n\n💵 Ціна: {message.text}".strip()
        ok = await update_service(data["service_id"], "description", value)
    else:
        ok = False

    await state.clear()
    await message.answer("✅ Зміни збережено" if ok else "❌ Не вдалося зберегти")


@router.callback_query(F.data.startswith("service_delete:"))
async def delete_handler(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    service_id = int(callback.data.split(":")[1])

    seller = await get_seller_by_telegram_id(callback.from_user.id)
    if not seller:
        await callback.message.answer("❌ Помилка продавця")
        return

    deleted = await delete_service_by_seller(service_id, seller["id"])
    if not deleted:
        await callback.message.answer("❌ Послугу не знайдено")
        return

    await callback.message.answer("🗑 Видалено")
    services = await get_services_by_seller(seller["id"])
    if services:
        await callback.message.answer("Оновлений список:", reply_markup=services_list_kb(services))
    else:
        await callback.message.answer("У вас немає послуг")
