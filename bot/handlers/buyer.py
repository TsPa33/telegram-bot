from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputMediaPhoto
)

from bot.database.repositories.model_repo import get_brands, get_models_by_brand
from bot.database.repositories.car_repo import find_cars, count_cars

from bot.services.car_service import get_model_or_none

from bot.states.buyer_states import Buyer
from bot.utils.validation import normalize_brand, normalize_model
from bot.utils.cache import get_cached_brands, get_cached_models

from bot.utils.formatters import format_car_card
from bot.keyboards.card_inline import build_card_keyboard

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    await state.clear()

    brands = await get_cached_brands(get_brands)

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
        resize_keyboard=True
    )

    await state.set_state(Buyer.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= GLOBAL BACK =================

@router.message(F.text == "⬅️ Назад")
async def global_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()

    if not current_state:
        await message.answer("🔙 Головне меню")
        return

    if current_state == Buyer.model:
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(Buyer.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    if current_state == Buyer.brand:
        await state.clear()
        await message.answer("🔙 Головне меню")
        return

    await state.clear()
    await message.answer("🔙 Головне меню")


# ================= BRAND =================

@router.message(Buyer.brand)
async def choose_brand(message: types.Message, state: FSMContext):
    text = message.text.strip()

    brand = normalize_brand(text)
    models = await get_cached_models(brand, get_models_by_brand)

    if not models:
        await message.answer("❌ Моделей немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=m)] for m in models] + [[BACK]],
        resize_keyboard=True
    )

    await state.update_data(brand=brand)
    await state.set_state(Buyer.model)
    await message.answer("🚘 Обери модель:", reply_markup=keyboard)


# ================= MODEL =================

@router.message(Buyer.model)
async def choose_model(message: types.Message, state: FSMContext):
    text = message.text.strip()
    model = normalize_model(text)

data = await state.get_data()
brand = data.get("brand")

# ===== ДІАГНОСТИКА =====
print("========== DEBUG ==========")
print("BRAND RAW:", brand)
print("MODEL RAW:", text)
print("MODEL NORMALIZED:", model)

model_id = await get_model_or_none(brand, model)

print("MODEL_ID:", model_id)
print("===========================")
# ===========================

if not brand:
    await state.clear()
    await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
    return

    total = await count_cars(model_id)

    if total == 0:
        await message.answer(
            "😕 Поки що немає оголошень для цієї моделі.\n"
            "Спробуй іншу модель або зайди пізніше."
        )
        return

    await state.update_data(
        model_id=model_id,
        page=0,
        total=total
    )

    await message.answer(f"🔎 Знайдено оголошень: {total}")

    await send_card(message, state, new_message=True)

    await state.set_state(None)


# ================= CARD =================

async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    model_id = data.get("model_id")
    page = data.get("page")
    total = data.get("total")

    if not all([model_id, total is not None]):
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    # 🔥 КЛЮЧОВИЙ ФІКС
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
        page = int(callback.data.split(":")[1])
    except:
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
