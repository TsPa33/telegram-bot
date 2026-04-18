from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import (
    get_cars_page,
    get_car_by_id,
    add_unique_car_view
)
from bot.database.base import execute
from bot.database.base import fetch

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard
from bot.keyboards.buyer_nav import buyer_nav_kb
from bot.keyboards.buyer_home import buyer_home_kb
from bot.keyboards.brands import brand_kb
from bot.keyboards.models import model_kb_with_back
from bot.keyboards.seller_menu import seller_main_kb


router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"

LIMIT = 1


# ================= CARD =================

async def send_card(message, state: FSMContext, new_message=False, user_id: int | None = None):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page", 1)
    total = data.get("total", 1)

    if not model_id:
        await state.set_state(None)
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    # 🔒 захист
    if page < 1:
        page = 1
    if page > total:
        page = total

    offset = (page - 1)

    cars = await get_cars_page(model_id, LIMIT, offset)

    if not cars:
        await message.answer("❌ Немає результатів")
        return

    car = cars[0]
    car_id = car["id"]

    viewer_id = user_id or message.chat.id
    await add_unique_car_view(car_id, viewer_id)

    text = format_car_card(car, page, total)
    keyboard = build_card_keyboard(car, page, total)

    new_photo = car.get("photo_id") or DEFAULT_PHOTO

    if new_message:
        await message.answer_photo(
            photo=new_photo,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await message.answer("Дії:", reply_markup=await buyer_nav_kb(viewer_id))
    else:
        try:
            current_photo = None

            # 📌 отримуємо поточне фото повідомлення
            if message.photo:
                current_photo = message.photo[-1].file_id

            # 🔥 якщо фото змінилось → edit_media
            if current_photo != new_photo:
                await message.edit_media(
                    media=InputMediaPhoto(
                        media=new_photo,
                        caption=text,
                        parse_mode="HTML"
                    ),
                    reply_markup=keyboard
                )
            else:
                # тільки текст
                await message.edit_caption(
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )

        except Exception:
            await message.answer_photo(
                photo=new_photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await message.answer("Дії:", reply_markup=await buyer_nav_kb(viewer_id))


# ================= NEXT =================

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


# ================= PREV =================

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


# ================= PHONE =================

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

    await callback.message.answer(f"📞 {car.get('phone') or 'не вказано'}")
    await callback.answer()


# ================= NOOP =================

@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "nav:restart")
async def restart_search(callback: CallbackQuery, state: FSMContext):
    print("NAV:", callback.data)

    await callback.answer()

    await state.clear()

    brands = await fetch(
        "SELECT id, name FROM brands ORDER BY name"
    )

    await callback.message.answer(
        "🔄 Перезапускаю пошук...",
        reply_markup=ReplyKeyboardRemove(),
    )

    await callback.message.answer(
        "🚗 Обери бренд",
        reply_markup=brand_kb(brands)
    )


@router.callback_query(F.data == "nav:back")
async def go_back(callback: CallbackQuery, state: FSMContext):
    print("NAV:", callback.data)

    await callback.answer()

    data = await state.get_data()

    if "model_id" in data and "brand_id" in data:
        models = await fetch(
            "SELECT id, name FROM models WHERE brand_id = $1 ORDER BY name",
            data["brand_id"]
        )

        await callback.message.answer(
            "🚘 Обери модель",
            reply_markup=model_kb_with_back(models)
        )
        return

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
    print("NAV:", callback.data)

    await callback.answer()

    await state.clear()

    await callback.message.answer(
        "🏪 Режим продавця\nОберіть дію:",
        reply_markup=seller_main_kb()
    )
