from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InputMediaPhoto

from bot.database.base import fetch
from bot.database.repositories.model_repo import get_brands_with_ids, get_models_by_brand_id
from bot.database.repositories.car_repo import find_cars, count_cars
from bot.database.repositories.request_repo import create_brand_request, create_model_request
from bot.config import ADMIN_IDS

from bot.states.buyer_states import Buyer, AddBrand, AddModel

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard
from bot.keyboards.brands import brand_kb
from bot.keyboards.models import model_kb

router = Router()

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.set_state(None)

    brands = await get_brands_with_ids()

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    await state.set_state(Buyer.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=brand_kb(brands))


# ================= BRAND =================

@router.callback_query(F.data.startswith("buyer:brand:"))
async def select_brand(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        brand_id = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Invalid brand", show_alert=True)
        return

    await state.update_data(brand_id=brand_id)

    models = await get_models_by_brand_id(brand_id)

    if not models:
        await state.set_state(Buyer.model)
        await callback.message.answer(
            "❌ Моделей немає\n\nМожеш додати свою 👇",
            reply_markup=model_kb([])
        )
        return

    await state.set_state(Buyer.model)
    await callback.message.answer(
        "🚘 Обери модель:",
        reply_markup=model_kb(models)
    )


# ================= ADD BRAND =================

@router.callback_query(F.data == "buyer:add_brand")
async def add_brand_request_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddBrand.waiting_for_brand)
    await callback.message.answer("✍️ Введи новий бренд (2-50 символів):")


@router.message(AddBrand.waiting_for_brand)
async def add_brand_request_save(message: types.Message, state: FSMContext):
    brand = _normalize_name(message.text)

    if not brand:
        await message.answer("❌ Введи коректний бренд (2-50 символів).")
        return

    created = await create_brand_request(message.from_user.id, brand)

    if not created:
        await message.answer("ℹ️ Така заявка вже існує або бренд вже погоджений.")
        await state.clear()
        return

    print("NEW BRAND REQUEST:", brand)

    await message.answer("✅ Заявку на бренд відправлено на модерацію.")

    await _notify_admins(
        message,
        f"New brand request: {brand}"
    )

    await state.clear()


# ================= ADD MODEL =================

@router.callback_query(F.data == "buyer:add_model")
async def add_model_request_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    brand_id = data.get("brand_id")

    if not brand_id:
        await callback.message.answer("❌ Спочатку обери бренд.")
        return

    brand_row = await fetch("""
        SELECT name
        FROM brands
        WHERE id = $1
        LIMIT 1
    """, brand_id)

    if not brand_row:
        await callback.message.answer("❌ Бренд не знайдено.")
        return

    await state.update_data(request_brand=brand_row[0]["name"])
    await state.set_state(AddModel.waiting_for_model)

    await callback.message.answer("✍️ Введи нову модель (2-50 символів):")


@router.message(AddModel.waiting_for_model)
async def add_model_request_save(message: types.Message, state: FSMContext):
    model = _normalize_name(message.text)

    if not model:
        await message.answer("❌ Введи коректну модель (2-50 символів).")
        return

    data = await state.get_data()
    brand = data.get("request_brand")

    if not brand:
        await message.answer("❌ Спочатку обери бренд.")
        await state.clear()
        return

    created = await create_model_request(message.from_user.id, brand, model)

    if not created:
        await message.answer("ℹ️ Така заявка вже існує або модель вже погоджена.")
        await state.clear()
        return

    print("NEW MODEL REQUEST:", model)

    await message.answer("✅ Заявку на модель відправлено на модерацію.")

    await _notify_admins(
        message,
        f"New model request: {brand} {model}"
    )

    await state.clear()


# ================= MODEL =================

@router.callback_query(F.data.startswith("buyer:model:"))
async def select_model(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    try:
        model_id = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Invalid model", show_alert=True)
        return

    model = await fetch(
        """
        SELECT id
        FROM models
        WHERE id = $1
        LIMIT 1
        """,
        model_id
    )

    if not model:
        await callback.message.answer("❌ Модель не знайдена")
        return

    total = await count_cars(model_id)

    if total == 0:
        await callback.message.answer(
            "😕 Поки що немає оголошень для цієї моделі."
        )
        return

    await state.update_data(
        model_id=model_id,
        page=0,
        total=total
    )

    await callback.message.answer(f"🔎 Знайдено оголошень: {total}")

    await send_card(callback.message, state, new_message=True)

    await state.set_state(None)


# ================= CARD =================

async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page")
    total = data.get("total")

    if not all([model_id, total is not None]):
        await state.set_state(None)
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    results = await find_cars(model_id, page, limit=1)

    if not results:
        await message.answer("❌ Більше немає результатів")
        return

    car = results[0]

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
    data = await state.get_data()

    if not data:
        await callback.answer("Сесія втрачена")
        return

    try:
        page = int(callback.data.split(":")[-1])
    except Exception:
        await callback.answer("Помилка")
        return

    total = data.get("total", 0)

    if page < 0 or page >= total:
        await callback.answer("Немає сторінки")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)


# ================= FALLBACK =================

@router.message(StateFilter(None))
async def fallback(message: types.Message):
    await message.answer("⚠️ Обери дію через меню або введи /find")


# ================= HELPERS =================

def _normalize_name(raw_value: str | None) -> str | None:
    if not raw_value:
        return None

    value = " ".join(raw_value.strip().split())

    if len(value) < 2 or len(value) > 50:
        return None

    return value.title()


async def _notify_admins(message: types.Message, text: str):
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, text)
        except Exception:
            continue