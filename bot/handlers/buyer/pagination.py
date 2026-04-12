from aiogram import Router, types, F
from aiogram.types import InputMediaPhoto
from aiogram.fsm.context import FSMContext

from bot.database.repositories.car_repo import find_cars
from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard


router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= CARD =================

async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    brand = data.get("brand")
    model = data.get("model")
    page = data.get("page")
    total = data.get("total")
    results = data.get("results")

    # 🔴 FSM consistency check
    if not all([brand, model, total is not None]):
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    # 🔴 PERFORMANCE: використовуємо кеш якщо є
    if not results:
        results = await find_cars(brand, model, 0, limit=10)

        if not results:
            await message.answer("❌ Більше немає результатів")
            return

        await state.update_data(
            results=results,
            total=len(results)
        )

    # 🔴 захист від виходу за межі
    if page < 0 or page >= len(results):
        await message.answer("❌ Більше немає результатів")
        return

    car = results[page]

    text = format_car_card(car, page, total)

    keyboard = build_card_keyboard(
        username=car.get("username"),
        page=page,
        total=total
    )

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
        except Exception:
            await message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )


# ================= PAGINATION =================

@router.callback_query(F.data.startswith("page:"))
async def paginate(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data:
        await callback.answer("Сесія втрачена")
        return

    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Помилка")
        return

    results = data.get("results")
    total = data.get("total", 0)

    # 🔴 якщо кеша немає — не даємо рухатись
    if not results:
        await callback.answer("Сесія втрачена")
        return

    if page < 0 or page >= total:
        await callback.answer("Немає сторінки")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)
