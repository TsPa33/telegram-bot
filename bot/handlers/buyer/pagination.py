from aiogram import Router, types, F
from aiogram.types import InputMediaPhoto
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import find_cars, count_cars, get_car_by_id
from bot.database.base import execute

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard


router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= CARD =================

async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page", 0)

    if not model_id:
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    total = await count_cars(model_id)

    if total == 0:
        await message.answer("❌ Немає результатів")
        return

    if page < 0 or page >= total:
        return

    results = await find_cars(model_id, page, limit=1)

    if not results:
        await message.answer("❌ Немає результатів")
        return

    car = results[0]

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
            await message.edit_media(
                InputMediaPhoto(
                    media=photo,
                    caption=text,
                    parse_mode="HTML"
                ),
                reply_markup=keyboard
            )
        except:
            await message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


# ================= PAGINATION =================

@router.callback_query(F.data.startswith("page:"))
async def paginate(callback: types.CallbackQuery, state: FSMContext):
    try:
        page = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)


# ================= PHONE =================

@router.callback_query(F.data.startswith("phone:"))
async def phone_click(callback: types.CallbackQuery):
    try:
        car_id = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    await execute("""
        UPDATE seller_cars
        SET phone_clicks = COALESCE(phone_clicks,0)+1
        WHERE id=$1
    """, car_id)

    await callback.answer()
    await callback.message.answer(f"📞 {car.get('phone') or 'не вказано'}")


# ================= SITE =================

@router.callback_query(F.data.startswith("site:"))
async def site_click(callback: types.CallbackQuery):
    try:
        car_id = int(callback.data.split(":")[1])
    except:
        await callback.answer("Помилка")
        return

    car = await get_car_by_id(car_id)

    if not car:
        await callback.answer("Не знайдено")
        return

    await execute("""
        UPDATE seller_cars
        SET site_clicks = COALESCE(site_clicks,0)+1
        WHERE id=$1
    """, car_id)

    await callback.answer()
    await callback.message.answer(f"🌐 {car.get('website') or 'не вказано'}")
