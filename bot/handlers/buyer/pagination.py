from aiogram import Router, F
from aiogram.types import CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import (
    get_first_car,
    get_next_car,
    get_prev_car,
    get_car_by_id
)
from bot.database.base import execute

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard


router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= CARD =================

async def send_card(message, state: FSMContext, new_message=False):
    data = await state.get_data()

    model_id = data.get("model_id")
    last_id = data.get("last_id")

    if not model_id:
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    # 🔥 перше авто
    if not last_id:
        car = await get_first_car(model_id)
    else:
        car = await get_next_car(model_id, last_id)

    if not car:
        await message.answer("❌ Немає результатів")
        return

    car_id = car["id"]

    await state.update_data(last_id=car_id)

    # views++
    await execute("""
        UPDATE seller_cars
        SET views = views + 1
        WHERE id = $1
    """, car_id)

    text = format_car_card(car)
    keyboard = build_card_keyboard(car)

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
            if message.photo and message.photo[-1].file_id == photo:
                await message.edit_caption(
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                await message.edit_media(
                    InputMediaPhoto(
                        media=photo,
                        caption=text,
                        parse_mode="HTML"
                    ),
                    reply_markup=keyboard
                )
        except Exception:
            await message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


# ================= NEXT =================

@router.callback_query(F.data == "next")
async def next_car(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await send_card(callback.message, state)


# ================= PREV =================

@router.callback_query(F.data.startswith("prev:"))
async def prev_car(callback: CallbackQuery, state: FSMContext):
    try:
        current_id = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    data = await state.get_data()
    model_id = data.get("model_id")

    car = await get_prev_car(model_id, current_id)

    if not car:
        await callback.answer("Це перше авто")
        return

    await state.update_data(last_id=car["id"])

    text = format_car_card(car)
    keyboard = build_card_keyboard(car)

    await callback.message.edit_caption(
        caption=text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )

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
