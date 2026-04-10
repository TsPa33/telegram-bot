from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import (
    brand_request_kb,
    model_request_kb
)

from bot.states.admin_states import AddUser

from bot.database.db import (
    add_user,
    get_pending_brand_requests,
    get_pending_model_requests,
    approve_brand,
    reject_brand,
    approve_model,
    reject_model
)

router = Router()


# ================= ADMIN PANEL =================

@router.message(F.text == "⚙️ Адмін панель")
async def open_admin_panel(message: types.Message):
    if message.from_user.id not in ADMINS:
        return

    await message.answer("Admin panel", reply_markup=admin_kb)


# ================= REQUESTS =================

@router.message(F.text == "📋 Заявки")
async def show_requests(message: types.Message):
    if message.from_user.id not in ADMINS:
        return

    # -------- бренди --------
    brand_requests = get_pending_brand_requests()

    if brand_requests:
        for req_id, user_id, brand in brand_requests:
            text = (
                f"🆕 Новий бренд\n\n"
                f"👤 User: {user_id}\n"
                f"🏷 Бренд: {brand}"
            )

            await message.answer(
                text,
                reply_markup=brand_request_kb(req_id)
            )

    # -------- моделі --------
    model_requests = get_pending_model_requests()

    if model_requests:
        for req_id, user_id, brand, model in model_requests:
            text = (
                f"🆕 Нова модель\n\n"
                f"👤 User: {user_id}\n"
                f"🚗 {brand} {model}"
            )

            await message.answer(
                text,
                reply_markup=model_request_kb(req_id)
            )

    if not brand_requests and not model_requests:
        await message.answer("✅ Немає заявок")


# ================= CALLBACK BRAND =================

@router.callback_query(F.data.startswith("brand_ok_"))
async def approve_brand_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    approve_brand(request_id)

    await callback.message.edit_text("✅ Бренд підтверджено")
    await callback.answer()


@router.callback_query(F.data.startswith("brand_no_"))
async def reject_brand_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    reject_brand(request_id)

    await callback.message.edit_text("❌ Бренд відхилено")
    await callback.answer()


# ================= CALLBACK MODEL =================

@router.callback_query(F.data.startswith("model_ok_"))
async def approve_model_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    approve_model(request_id)

    await callback.message.edit_text("✅ Модель підтверджено")
    await callback.answer()


@router.callback_query(F.data.startswith("model_no_"))
async def reject_model_cb(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    reject_model(request_id)

    await callback.message.edit_text("❌ Модель відхилено")
    await callback.answer()


# ================= ADD USER =================

@router.message(lambda m: m.text == "➕ Додати користувача")
async def add_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    await message.answer("Введіть ім'я користувача:")
    await state.set_state(AddUser.name)


# 1️⃣ ІМ'Я → САЙТ
@router.message(AddUser.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введіть посилання на сайт:")
    await state.set_state(AddUser.website)


# 2️⃣ САЙТ → ТЕЛЕФОН
@router.message(AddUser.website)
async def get_website(message: types.Message, state: FSMContext):
    await state.update_data(website=message.text.strip())
    await message.answer("Введіть номер телефону:")
    await state.set_state(AddUser.phone)


# 3️⃣ ТЕЛЕФОН → МОДЕЛІ
@router.message(AddUser.phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())

    await message.answer(
        "Введіть моделі у форматі:\n\n"
        "Model: Audi\n"
        "A4\n"
        "A6\n\n"
        "Model: BMW\n"
        "E60\n"
        "F30\n\n"
        "(кожна модель з нового рядка)"
    )

    await state.set_state(AddUser.models)


# 4️⃣ МОДЕЛІ → ЗБЕРЕЖЕННЯ
@router.message(AddUser.models)
async def get_models(message: types.Message, state: FSMContext):
    text = message.text

    if "model:" not in text.lower():
        await message.answer("❌ Використай формат з 'Model:'")
        return

    lines = text.split("\n")

    current_brand = None
    data_dict = {}

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line.lower().startswith("model:"):
            current_brand = line.split(":", 1)[1].strip().title()

            if current_brand not in data_dict:
                data_dict[current_brand] = []

        else:
            if current_brand:
                model = line.strip().upper()

                if model not in data_dict[current_brand]:
                    data_dict[current_brand].append(model)

    if not data_dict:
        await message.answer("❌ Не вдалося розпарсити моделі")
        return

    await state.update_data(models=data_dict)
    data = await state.get_data()

    try:
        add_user(data)
        await message.answer("✅ Користувача додано")
    except Exception as e:
        await message.answer(f"❌ Помилка: {str(e)}")

    await state.clear()
