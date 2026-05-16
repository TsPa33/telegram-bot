import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.services.car_service import get_cars_page
from bot.database.repositories.car_repo import (
    get_car_by_id,
    add_unique_car_view
)
from bot.database.repositories.buyer_repo import (
    add_history,
    create_buyer_request,
    is_favorite,
)
from bot.database.base import execute
from bot.database.base import fetch

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard, normalize_url
from bot.keyboards.buyer_nav import buyer_nav_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.brands import brand_kb
from bot.keyboards.models import model_kb_with_back
from bot.keyboards.seller_menu import seller_main_kb
from bot.keyboards.buyer_reply import buyer_reply_kb
from bot.keyboards.buyer_search_inline import (
    format_search_card,
    format_search_details,
    search_result_kb,
)

router = Router()
logger = logging.getLogger(__name__)

LIMIT = 1


async def send_card(message, state: FSMContext, new_message=False, user_id: int | None = None):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page", 1)
    total = data.get("total", 1)

    if not model_id:
        await state.set_state(None)
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    car, total_pages = await get_cars_page(model_id, page, LIMIT)

    if total_pages != total:
        total = total_pages
        await state.update_data(total=total_pages)

    if not car:
        await message.answer("❌ Немає результатів")
        return

    car_id = car["id"]

    viewer_id = user_id or message.chat.id

    await add_unique_car_view(car_id, viewer_id)
    await add_history(viewer_id, "car", str(car_id))
    if car.get("seller_id"):
        await add_history(viewer_id, "seller", str(car["seller_id"]))

    is_owner = car.get("seller_id") == viewer_id

    text = format_car_card(
        car,
        page,
        total,
        is_owner=is_owner
    )

    keyboard = build_card_keyboard(
        car,
        page,
        total,
        is_car_favorite=await is_favorite(viewer_id, "car", str(car_id)),
        is_seller_favorite=await is_favorite(viewer_id, "seller", str(car.get("seller_id"))),
        is_website_favorite=await is_favorite(viewer_id, "website", str(normalize_url(car.get("website")))),
    )

    new_photo = car.get("photo_id")

    if new_message:
        if new_photo:
            try:
                await message.answer_photo(
                    photo=new_photo,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except TelegramBadRequest as exc:
                logger.warning("Car photo unavailable for buyer card %s: %s", car_id, exc)
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

        await message.answer("Дії:", reply_markup=await buyer_nav_kb(viewer_id))
    else:
        try:
            current_photo = None

            if message.photo:
                current_photo = message.photo[-1].file_id

            if new_photo and current_photo != new_photo:
                await message.edit_media(
                    media=InputMediaPhoto(
                        media=new_photo,
                        caption=text,
                        parse_mode="HTML"
                    ),
                    reply_markup=keyboard
                )
            elif message.photo:
                await message.edit_caption(
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await message.edit_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

        except Exception as exc:
            logger.warning("Unable to update buyer card %s, sending a new message: %s", car_id, exc)
            if new_photo:
                try:
                    await message.answer_photo(
                        photo=new_photo,
                        caption=text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                except TelegramBadRequest as photo_exc:
                    logger.warning("Car photo unavailable for buyer card %s: %s", car_id, photo_exc)
                    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

            await message.answer("Дії:", reply_markup=await buyer_nav_kb(viewer_id))


@router.callback_query(F.data == "next")
async def next_car(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    page = data.get("page", 1)
    total = data.get("total", 1)

    if page >= total:
        await callback.answer("Це остання сторінка")
        return

    page += 1
    await state.update_data(page=page)

    await send_card(callback.message, state, user_id=callback.from_user.id)

    await callback.answer()


@router.callback_query(F.data == "prev")
async def prev_car(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    page = data.get("page", 1)

    if page <= 1:
        await callback.answer("Це перша сторінка")
        return

    page -= 1
    await state.update_data(page=page)

    await send_card(callback.message, state, user_id=callback.from_user.id)

    await callback.answer()


@router.callback_query(F.data.startswith("phone:"))
async def phone_click(callback: CallbackQuery):
    car_id = int(callback.data.split(":")[1])

    await execute("""
        UPDATE seller_cars
        SET phone_clicks = phone_clicks + 1
        WHERE id = $1
    """, car_id)

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    await create_buyer_request(
        telegram_id=callback.from_user.id,
        request_type="car_phone",
        entity_type="car",
        entity_ref=str(car_id),
        seller_id=car.get("seller_id"),
        message="Buyer opened seller phone from car card",
    )

    await callback.message.answer(f"📞 {car.get('phone') or 'не вказано'}")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "nav:restart")
async def restart_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    brands = await fetch(
        "SELECT id, name FROM brands ORDER BY name"
    )

    await callback.message.answer(
        "🔄 Перезапускаю пошук...",
        reply_markup=buyer_reply_kb(),
    )

    await callback.message.answer(
        "🚗 Обери бренд",
        reply_markup=brand_kb(brands)
    )


@router.callback_query(F.data == "nav:back")
async def go_back(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()

    if "model_id" in data:
        await state.update_data(model_id=None)

    if "brand_id" in data:
        brands = await fetch(
            "SELECT id, name FROM brands ORDER BY name"
        )

        await callback.message.answer(
            "🚗 Обери бренд",
            reply_markup=brand_kb(brands)
        )
        return

    await callback.message.answer(
        "🏠 <b>Головне меню покупця</b>\n\n"
        "👤 Профіль\n"
        "🚗 Знайти авто\n"
        "👀 Мої перегляди\n"
        "⭐ Обрані",
        parse_mode="HTML",
        reply_markup=buyer_home_kb(),
    )


@router.callback_query(F.data == "nav:seller")
@router.callback_query(F.data == "nav:garage")
async def go_seller(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "🔄 Перемикаю у режим продавця...",
        reply_markup=ReplyKeyboardRemove(),
    )
    await callback.message.answer(
        "🏪 Режим продавця\nОберіть дію:",
        reply_markup=seller_main_kb()
    )


def _buyer_search_item(data: dict, item_type: str, item_id: str) -> dict | None:
    for item in data.get("buyer_search_items") or []:
        if str(item.get("_type")) == item_type and str(item.get("id")) == str(item_id):
            return item
    return None


def _buyer_search_request_message(data: dict, item: dict | None = None) -> str:
    query = str(data.get("buyer_search_query") or "").strip()
    if item:
        title = item.get("description") or item.get("title") or item.get("shop_name") or item.get("name")
        if title:
            return f"Покупець цікавиться: {title}"
    if query:
        return f"Покупець шукає: {query}"
    return "Покупець створив заявку з Telegram-пошуку CarPot"


async def _show_buyer_search_page(callback: CallbackQuery, state: FSMContext, page: int):
    data = await state.get_data()
    items = data.get("buyer_search_items") or []
    total = len(items)

    if not items:
        await callback.answer("Сесія пошуку завершена")
        return

    safe_page = max(1, min(int(page or 1), total))
    item = items[safe_page - 1]
    item_type = item.get("_type", "car")
    await state.update_data(buyer_search_page=safe_page)

    try:
        await callback.message.edit_text(
            format_search_card(item, item_type),
            parse_mode="HTML",
            reply_markup=search_result_kb(item, item_type, page=safe_page, total=total),
        )
    except Exception as exc:
        logger.warning("Unable to edit buyer search card page=%s: %s", safe_page, exc)
        await callback.message.answer(
            format_search_card(item, item_type),
            parse_mode="HTML",
            reply_markup=search_result_kb(item, item_type, page=safe_page, total=total),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_search:next:"))
async def buyer_search_next(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[-1])
    await _show_buyer_search_page(callback, state, page)


@router.callback_query(F.data.startswith("buyer_search:prev:"))
async def buyer_search_prev(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[-1])
    await _show_buyer_search_page(callback, state, page)


@router.callback_query(F.data.startswith("buyer_search:details:"))
async def buyer_search_details(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Не вдалося відкрити деталі")
        return

    item_type, item_id = parts[2], parts[3]
    data = await state.get_data()
    item = _buyer_search_item(data, item_type, item_id)
    if not item:
        await callback.answer("Результат більше недоступний")
        return

    await callback.message.answer(format_search_details(item, item_type), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_search:ask:"))
async def buyer_search_ask(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Не вдалося створити звернення")
        return

    item_type, item_id = parts[2], parts[3]
    data = await state.get_data()
    item = _buyer_search_item(data, item_type, item_id)
    if not item:
        await callback.answer("Результат більше недоступний")
        return

    request = await create_buyer_request(
        telegram_id=callback.from_user.id,
        request_type=f"search_{item_type}_ask",
        entity_type=item_type,
        entity_ref=str(item_id),
        seller_id=item.get("seller_id") or (item.get("id") if item_type == "seller" else None),
        message=_buyer_search_request_message(data, item),
    )
    if request:
        await callback.message.answer("✅ Звернення створено. Продавець побачить ваш інтерес у заявках.")
    else:
        await callback.message.answer("⚠️ Не вдалося створити звернення. Спробуйте створити заявку.")
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_search:create_request:"))
async def buyer_search_create_request(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    item_type = parts[2] if len(parts) > 2 else "fallback"
    item_id = parts[3] if len(parts) > 3 else "0"
    data = await state.get_data()
    item = _buyer_search_item(data, item_type, item_id) if item_type != "fallback" else None

    request = await create_buyer_request(
        telegram_id=callback.from_user.id,
        request_type="search_request",
        entity_type=item_type if item_type != "fallback" else "marketplace_search",
        entity_ref=str(item_id),
        seller_id=(item or {}).get("seller_id") or ((item or {}).get("id") if item_type == "seller" else None),
        message=_buyer_search_request_message(data, item),
    )
    if request:
        await callback.message.answer(
            f"✅ Заявку створено #{request['id']}.\n\nВідкрити історію можна в «Мої заявки».",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Мої заявки", callback_data="buyer:requests")]]
            ),
        )
    else:
        await callback.message.answer("⚠️ Не вдалося створити заявку. Спробуйте ще раз.")
    await callback.answer()


@router.callback_query(F.data == "buyer_search:noop")
async def buyer_search_noop(callback: CallbackQuery):
    await callback.answer()
