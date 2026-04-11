from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto
)

from bot.database.repositories.model_repo import get_brands, get_models_by_brand
from bot.database.repositories.car_repo import find_cars, count_cars

from bot.states.buyer_states import Buyer
from bot.utils.validation import normalize_brand, normalize_model
from bot.utils.cache import get_cached_brands, get_cached_models

router = Router()

BACK = KeyboardButton(text="⬅️ Назад")

DEFAULT_PHOTO = "AgACAgIAAxkBAAIJ6WnZ7zNsTF4dV6Fxbqsye8iRF224AAJfEWsbFN_RSsup93hjz4uMAQADAgADeAADOwQ"


# ================= START =================

@router.message(Command("find"))
async def start_buyer(message: types.Message, state: FSMContext):
    brands = await get_cached_brands(get_brands)

    if not brands:
        await message.answer("❌ Брендів немає")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
        resize_keyboard=True
    )

    await state.clear()
    await state.set_state(Buyer.brand)
    await message.answer("🚗 Обери бренд:", reply_markup=keyboard)


# ================= BRAND =================

@router.message(Buyer.brand)
async def choose_brand(message: types.Message, state: FSMContext):
    text = message.text.strip()

    if text == "⬅️ Назад":
        await state.clear()
        await message.answer("🔙 Головне меню")
        return

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

    if text == "⬅️ Назад":
        brands = await get_cached_brands(get_brands)

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=b)] for b in brands] + [[BACK]],
            resize_keyboard=True
        )

        await state.set_state(Buyer.brand)
        await message.answer("🚗 Обери бренд:", reply_markup=keyboard)
        return

    model = normalize_model(text)

    data = await state.get_data()
    brand = data.get("brand")

    if not brand:
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    total = await count_cars(brand, model)

    if total == 0:
        await message.answer("❌ Нічого не знайдено")
        return

    await state.update_data(model=model, page=0, total=total)

    await send_card(message, state, new_message=True)


# ================= CARD =================

async def send_card(message: types.Message, state: FSMContext, new_message=False):
    data = await state.get_data()

    brand = data.get("brand")
    model = data.get("model")
    page = data.get("page")
    total = data.get("total")

    if not all([brand, model, total is not None]):
        await state.clear()
        await message.answer("⚠️ Сесія втрачена. Почни заново: /find")
        return

    results = await find_cars(brand, model, page, limit=1)

    if not results:
        await message.answer("❌ Більше немає результатів")
        return

    car = results[0]

    username = car["username"]
    brand_db = car["brand"]
    model_db = car["model"]
    photo_id = car["photo_id"]
    description = car.get("description", "")

    username_display = f"@{username}" if username else "не вказано"

    text = (
        f"🚗 <b>{brand_db} {model_db}</b>\n\n"
        f"{description}\n\n"
        f"👤 Продавець: {username_display}\n"
        f"📄 {page + 1} / {total}"
    )

    kb = build_card_kb(username, page, total)

    if new_message:
        await message.answer_photo(
            photo_id or DEFAULT_PHOTO,
            caption=text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        try:
            await message.edit_media(
                InputMediaPhoto(
                    media=photo_id or DEFAULT_PHOTO,
                    caption=text,
                    parse_mode="HTML"
                ),
                reply_markup=kb
            )
        except:
            # fallback якщо Telegram не дає edit
            await message.answer_photo(
                photo_id or DEFAULT_PHOTO,
                caption=text,
                reply_markup=kb,
                parse_mode="HTML"
            )


# ================= KEYBOARD =================

def build_card_kb(username: str | None, page: int, total: int):
    buttons = []

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data="prev"))

    if page < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data="next"))

    if nav:
        buttons.append(nav)

    if username:
        buttons.append([
            InlineKeyboardButton(
                text="📩 Написати",
                url=f"https://t.me/{username}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ================= PAGINATION =================

@router.callback_query(F.data == "next")
async def next_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data:
        await callback.answer("Сесія втрачена")
        return

    page = data.get("page", 0) + 1
    total = data.get("total", 0)

    if page >= total:
        await callback.answer("Кінець")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)


@router.callback_query(F.data == "prev")
async def prev_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data:
        await callback.answer("Сесія втрачена")
        return

    page = data.get("page", 0) - 1

    if page < 0:
        await callback.answer("Початок")
        return

    await state.update_data(page=page)

    await callback.answer()
    await send_card(callback.message, state)
