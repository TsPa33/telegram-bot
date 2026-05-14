import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database.base import fetchrow
from bot.database.repositories.buyer_repo import (
    add_garage_entry,
    delete_favorite,
    delete_garage_entry,
    get_buyer_request,
    get_favorite,
    get_garage_entry,
    is_favorite,
    list_buyer_requests,
    list_favorites,
    list_garage,
    list_history,
    toggle_favorite,
    update_buyer_request_status,
)
from bot.database.repositories.car_repo import get_car_by_id
from bot.database.repositories.service_repo import get_service_by_id
from bot.utils.formatters import format_car_card
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.buyer_reply import buyer_reply_kb
from bot.keyboards.card_inline import normalize_url
from bot.states.buyer_states import Buyer

from .pagination import send_card

router = Router()

STATUS_LABELS = {
    "new": "🆕 нова",
    "viewed": "👀 переглянута",
    "answered": "✅ відповідь",
    "closed": "🔒 закрита",
}

FAVORITE_LABELS = {
    "car": "🚗 Авто",
    "seller": "🏪 Продавець",
    "service": "🛠 Послуга",
    "website": "🌐 Сайт",
}


async def _get_model_for_vehicle(vehicle_name: str):
    query = f"%{vehicle_name.strip().lower()}%"
    return await fetchrow(
        """
        SELECT m.id, b.name AS brand, m.name AS model
        FROM models m
        JOIN brands b ON b.id = m.brand_id
        WHERE LOWER(b.name || ' ' || m.name) LIKE $1
           OR LOWER(m.name) LIKE $1
        ORDER BY m.id DESC
        LIMIT 1
        """,
        query,
    )


def _back_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📱 Моє меню", callback_data="nav:home")]]
    )


def garage_kb(entries) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Додати авто", callback_data="garage:add")]]
    for entry in entries[:10]:
        rows.append([
            InlineKeyboardButton(text=f"🔎 {entry['vehicle_name']}", callback_data=f"garage:search:{entry['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"garage:remove:{entry['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="📱 Моє меню", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def favorites_kb(favorites) -> InlineKeyboardMarkup:
    rows = []
    for favorite in favorites[:20]:
        label = FAVORITE_LABELS.get(favorite["entity_type"], favorite["entity_type"])
        rows.append([
            InlineKeyboardButton(
                text=f"{label} #{favorite['entity_ref']}",
                callback_data=f"favorite:open:{favorite['id']}",
            ),
            InlineKeyboardButton(
                text="💔",
                callback_data=f"favorite:remove:{favorite['id']}",
            ),
        ])
    rows.append([InlineKeyboardButton(text="📱 Моє меню", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def requests_kb(requests) -> InlineKeyboardMarkup:
    rows = []
    for request in requests[:20]:
        status = STATUS_LABELS.get(request["status"], request["status"])
        rows.append([
            InlineKeyboardButton(
                text=f"#{request['id']} · {status}",
                callback_data=f"buyer:req:open:{request['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="📱 Моє меню", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "buyer:favorites")
async def show_favorites(callback: CallbackQuery):
    favorites = await list_favorites(callback.from_user.id)
    await callback.answer()

    if not favorites:
        await callback.message.answer(
            "❤️ Обране\n\nТут будуть збережені авто, продавці, послуги та сайти.",
            reply_markup=_back_home_kb(),
        )
        return

    await callback.message.answer(
        "❤️ Обране\n\nШвидкий доступ до важливого:",
        reply_markup=favorites_kb(favorites),
    )


@router.callback_query(F.data.startswith("favorite:open:"))
async def open_favorite(callback: CallbackQuery):
    favorite_id = int(callback.data.split(":")[-1])
    favorite = await get_favorite(favorite_id, callback.from_user.id)
    await callback.answer()

    if not favorite:
        await callback.message.answer("Обране не знайдено.", reply_markup=_back_home_kb())
        return

    entity_type = favorite["entity_type"]
    entity_ref = favorite["entity_ref"]

    if entity_type == "car":
        car = await get_car_by_id(int(entity_ref))
        if not car:
            await callback.message.answer("Авто більше не доступне.", reply_markup=_back_home_kb())
            return
        await callback.message.answer(format_car_card(car, 1, 1), parse_mode="HTML", reply_markup=_back_home_kb())
        return

    if entity_type == "service":
        service = await get_service_by_id(int(entity_ref))
        if not service:
            await callback.message.answer("Послуга більше не доступна.", reply_markup=_back_home_kb())
            return
        await callback.message.answer(
            f"🛠 {service['title']}\n📍 {service['city']}\n📌 {service['address']}\n\n{service.get('description') or 'Опис відсутній'}",
            reply_markup=_back_home_kb(),
        )
        return

    if entity_type == "seller":
        seller = await fetchrow(
            """
            SELECT id, shop_name, name, username, phone, city, website
            FROM sellers
            WHERE id = $1
            LIMIT 1
            """,
            int(entity_ref),
        )
        if not seller:
            await callback.message.answer("Продавець більше не доступний.", reply_markup=_back_home_kb())
            return
        username = f"@{seller['username']}" if seller.get("username") else "—"
        await callback.message.answer(
            "🏪 Продавець\n\n"
            f"Назва: {seller.get('shop_name') or seller.get('name') or '—'}\n"
            f"Місто: {seller.get('city') or '—'}\n"
            f"Телефон: {seller.get('phone') or '—'}\n"
            f"Telegram: {username}",
            reply_markup=_back_home_kb(),
        )
        return

    if entity_type == "website":
        await callback.message.answer(
            "🌐 Збережений сайт",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Відкрити", url=entity_ref)],
                    [InlineKeyboardButton(text="📱 Моє меню", callback_data="nav:home")],
                ]
            ),
        )


@router.callback_query(F.data.startswith("favorite:remove:"))
async def remove_favorite(callback: CallbackQuery):
    favorite_id = int(callback.data.split(":")[-1])
    removed = await delete_favorite(favorite_id, callback.from_user.id)
    await callback.answer("Прибрано з обраного" if removed else "Не знайдено")
    favorites = await list_favorites(callback.from_user.id)
    await callback.message.answer(
        "❤️ Обране" if favorites else "❤️ Обране\n\nСписок порожній.",
        reply_markup=favorites_kb(favorites) if favorites else _back_home_kb(),
    )


@router.callback_query(F.data.startswith("fav:toggle:"))
async def toggle_favorite_handler(callback: CallbackQuery):
    parts = callback.data.split(":", 3)
    if len(parts) != 4:
        await callback.answer("Некоректна дія", show_alert=True)
        return

    _, _, entity_type, entity_ref = parts
    store_ref = entity_ref

    if entity_type == "website":
        car = await get_car_by_id(int(entity_ref))
        store_ref = normalize_url(car.get("website") if car else None) or entity_ref

    is_added = await toggle_favorite(callback.from_user.id, entity_type, store_ref)
    await callback.answer("Додано в обране" if is_added else "Прибрано з обраного")


@router.callback_query(F.data == "buyer:requests")
async def show_requests(callback: CallbackQuery):
    requests = await list_buyer_requests(callback.from_user.id)
    await callback.answer()

    if not requests:
        await callback.message.answer(
            "📩 Мої заявки\n\nТут зʼявиться історія звернень до продавців і сервісів.",
            reply_markup=_back_home_kb(),
        )
        return

    await callback.message.answer(
        "📩 Мої заявки\n\nСтатуси оновлюються в CRM:",
        reply_markup=requests_kb(requests),
    )


@router.callback_query(F.data.startswith("buyer:req:open:"))
async def open_request(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])
    request = await get_buyer_request(request_id, callback.from_user.id)
    await callback.answer()

    if not request:
        await callback.message.answer("Заявку не знайдено.", reply_markup=_back_home_kb())
        return

    if request["status"] == "new":
        await update_buyer_request_status(request_id, callback.from_user.id, "viewed")

    seller = request.get("shop_name") or request.get("seller_name") or request.get("seller_username") or "—"
    created_at = request["created_at"].strftime("%d.%m.%Y %H:%M") if request.get("created_at") else "—"
    text = (
        f"📩 Заявка #{request['id']}\n\n"
        f"Статус: {STATUS_LABELS.get(request['status'], request['status'])}\n"
        f"Тип: {request['request_type']}\n"
        f"Обʼєкт: {request['entity_type']} #{request['entity_ref']}\n"
        f"Продавець/сервіс: {seller}\n"
        f"Створено: {created_at}\n"
    )
    await callback.message.answer(text, reply_markup=_back_home_kb())


@router.callback_query(F.data == "buyer:garage")
async def show_garage(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    entries = await list_garage(callback.from_user.id)
    await callback.answer()

    text = "🚘 Мій гараж\n\nЗбережи авто, які цікавлять, щоб швидко повертатися до пошуку."
    if entries:
        text += "\n\n" + "\n".join(f"• {entry['vehicle_name']}" for entry in entries[:10])

    await callback.message.answer(text, reply_markup=garage_kb(entries))


@router.callback_query(F.data == "garage:add")
async def garage_add(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(Buyer.garage_vehicle)
    await callback.message.answer(
        "🚘 Напиши авто одним повідомленням.\n\nНаприклад: Volkswagen Passat B7, BMW E60, Audi A6 C7",
        reply_markup=buyer_reply_kb(),
    )


@router.message(Buyer.garage_vehicle)
async def garage_save(message: Message, state: FSMContext):
    vehicle_name = (message.text or "").strip()
    if len(vehicle_name) < 2:
        await message.answer("Напиши назву авто трохи детальніше.")
        return

    await add_garage_entry(message.from_user.id, vehicle_name[:120])
    await state.clear()
    entries = await list_garage(message.from_user.id)
    await message.answer("✅ Авто додано в гараж.", reply_markup=garage_kb(entries))


@router.callback_query(F.data.startswith("garage:remove:"))
async def garage_remove(callback: CallbackQuery):
    entry_id = int(callback.data.split(":")[-1])
    removed = await delete_garage_entry(entry_id, callback.from_user.id)
    entries = await list_garage(callback.from_user.id)
    await callback.answer("Видалено" if removed else "Не знайдено")
    await callback.message.answer("🚘 Мій гараж", reply_markup=garage_kb(entries))


@router.callback_query(F.data.startswith("garage:search:"))
async def garage_search(callback: CallbackQuery, state: FSMContext):
    entry_id = int(callback.data.split(":")[-1])
    entry = await get_garage_entry(entry_id, callback.from_user.id)
    await callback.answer()

    if not entry:
        await callback.message.answer("Авто не знайдено в гаражі.", reply_markup=_back_home_kb())
        return

    model = await _get_model_for_vehicle(entry["vehicle_name"])
    if not model:
        await callback.message.answer(
            "Поки не знайшов точний збіг у каталозі. Натисни «🚗 Знайти авто» та обери бренд вручну.",
            reply_markup=buyer_home_kb(),
        )
        return

    total_items = await fetchrow(
        "SELECT COUNT(*) AS total FROM seller_cars WHERE model_id = $1 AND status = 'active'",
        model["id"],
    )
    total = total_items["total"] if total_items else 0
    if total == 0:
        await callback.message.answer("Для цього авто зараз немає активних оголошень.", reply_markup=_back_home_kb())
        return

    await state.update_data(model_id=model["id"], page=1, total=max(1, math.ceil(total)))
    await send_card(callback.message, state, new_message=True, user_id=callback.from_user.id)
    await state.set_state(None)


@router.callback_query(F.data == "buyer:profile")
@router.callback_query(F.data == "buyer:views")
async def show_profile(callback: CallbackQuery):
    history = await list_history(callback.from_user.id, limit=5)
    favorites = await list_favorites(callback.from_user.id, limit=1)
    requests = await list_buyer_requests(callback.from_user.id, limit=1)
    garage = await list_garage(callback.from_user.id)
    await callback.answer()

    lines = [
        "👤 Профіль покупця",
        "",
        f"❤️ Обране: {'є' if favorites else 'поки порожньо'}",
        f"📩 Заявки: {'є' if requests else 'поки немає'}",
        f"🚘 Гараж: {len(garage)} авто",
        "",
        "🕘 Останні перегляди:",
    ]
    if history:
        lines.extend(f"• {item['entity_type']} #{item['entity_ref']}" for item in history)
    else:
        lines.append("• поки немає")

    await callback.message.answer("\n".join(lines), reply_markup=buyer_home_kb())
