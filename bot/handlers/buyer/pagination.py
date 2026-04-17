from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import (
    get_cars_page,
    get_car_by_id
)
from bot.database.base import execute

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard


router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"

LIMIT = 1


# ================= CARD =================

async def send_card(message, state: FSMContext, new_message=False):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page", 1)
    total = data.get("total", 1)

    if not model_id:
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    # 🔒 захист від кривих значень
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

    # views++
    await execute("""
        UPDATE seller_cars
        SET views = views + 1
        WHERE id = $1
    """, car_id)

    text = format_car_card(car, page, total)
    keyboard = build_card_keyboard(car, page, total)

    photo = car.get("photo_id") or DEFAULT_PHOTO

    if new_message:
        await message.answer_photo(
            photo=photo,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        try:
            await message.edit_caption(
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception:
            # fallback якщо Telegram не дає edit
            await message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


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

    await send_card(callback.message, state)

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

    await send_card(callback.message, state)

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
