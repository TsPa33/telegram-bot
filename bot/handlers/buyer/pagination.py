from aiogram import Router, types, F
from aiogram.types import InputMediaPhoto
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import find_cars, get_car_by_id
from bot.database.base import execute

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard


router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    brand = data.get("brand")
    model = data.get("model")
    page = data.get("page", 0)
    results = data.get("results")

    if not brand or not model:
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    if not results:
        results = await find_cars(brand, model, 0, limit=10)

        if not results:
            await message.answer("❌ Немає результатів")
            return

        await state.update_data(results=results)

    total = len(results)

    if page < 0 or page >= total:
        return

    car = results[page]

    # VIEW
    await execute("""
        UPDATE seller_cars
        SET views = COALESCE(views,0)+1
        WHERE id=$1
    """, car["id"])

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


@router.callback_query(F.data.startswith("page:"))
async def paginate(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    results = data.get("results")

    if not results:
        await callback.answer("Сесія втрачена")
        return

    page = int(callback.data.split(":")[1])

    if page < 0 or page >= len(results):
        await callback.answer("Немає сторінки")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)


@router.callback_query(F.data.startswith("phone:"))
async def phone_click(callback: types.CallbackQuery):
    car_id = int(callback.data.split(":")[1])

    car = await get_car_by_id(car_id)

    await execute("""
        UPDATE seller_cars
        SET phone_clicks = COALESCE(phone_clicks,0)+1
        WHERE id=$1
    """, car_id)

    await callback.answer()
    await callback.message.answer(f"📞 {car.get('phone')}")


@router.callback_query(F.data.startswith("site:"))
async def site_click(callback: types.CallbackQuery):
    car_id = int(callback.data.split(":")[1])

    car = await get_car_by_id(car_id)

    await execute("""
        UPDATE seller_cars
        SET site_clicks = COALESCE(site_clicks,0)+1
        WHERE id=$1
    """, car_id)

    await callback.answer()
    await callback.message.answer(f"🌐 {car.get('website')}")
