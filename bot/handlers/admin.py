from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import (
    brand_request_kb,
    model_request_kb
)

from bot.states.admin_states import AddUser, EditBrand, EditModel

from bot.database.db import (
    add_user,
    get_pending_brand_requests,
    get_pending_model_requests,
    approve_brand,
    reject_brand,
    approve_model,
    reject_model,
    update_brand_request,
    update_model_request
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

    brand_requests = get_pending_brand_requests()
    model_requests = get_pending_model_requests()

    if brand_requests:
        for req_id, user_id, brand in brand_requests:
            await message.answer(
                f"🆕 Новий бренд\n\n👤 User: {user_id}\n🏷 Бренд: {brand}",
                reply_markup=brand_request_kb(req_id)
            )

    if model_requests:
        for req_id, user_id, brand, model in model_requests:
            await message.answer(
                f"🆕 Нова модель\n\n👤 User: {user_id}\n🚗 {brand} {model}",
                reply_markup=model_request_kb(req_id)
            )

    if not brand_requests and not model_requests:
        await message.answer("✅ Немає заявок")


# ================= BRAND ACTIONS =================

@router.callback_query(F.data.startswith("brand_ok_"))
async def approve_brand_cb(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    # беремо дані ДО approve
    brand_requests = get_pending_brand_requests()

    user_id = None
    brand = None

    for r in brand_requests:
        if r[0] == request_id:
            _, user_id, brand = r
            break

    approve_brand(request_id)

    if user_id:
        try:
            await bot.send_message(user_id, f"✅ Ваш бренд підтверджено: {brand}")
        except:
            pass

    await callback.message.edit_text("✅ Бренд підтверджено")
    await callback.answer()


@router.callback_query(F.data.startswith("brand_no_"))
async def reject_brand_cb(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    brand_requests = get_pending_brand_requests()

    user_id = None
    brand = None

    for r in brand_requests:
        if r[0] == request_id:
            _, user_id, brand = r
            break

    reject_brand(request_id)

    if user_id:
        try:
            await bot.send_message(user_id, f"❌ Ваш бренд відхилено: {brand}")
        except:
            pass

    await callback.message.edit_text("❌ Бренд відхилено")
    await callback.answer()


# ================= EDIT BRAND =================

@router.callback_query(F.data.startswith("brand_edit_"))
async def edit_brand_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    await state.update_data(request_id=request_id)
    await callback.message.answer("✏️ Введіть правильну назву бренду:")
    await state.set_state(EditBrand.waiting_for_new_brand)

    await callback.answer()


@router.message(EditBrand.waiting_for_new_brand)
async def edit_brand_save(message: types.Message, state: FSMContext):
    new_brand = message.text.strip().title()

    data = await state.get_data()
    request_id = data.get("request_id")

    update_brand_request(request_id, new_brand)
    approve_brand(request_id)

    await message.answer(f"✅ Бренд виправлено та підтверджено: {new_brand}")

    await state.clear()


# ================= MODEL ACTIONS =================

@router.callback_query(F.data.startswith("model_ok_"))
async def approve_model_cb(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    model_requests = get_pending_model_requests()

    user_id = None
    brand = None
    model = None

    for r in model_requests:
        if r[0] == request_id:
            _, user_id, brand, model = r
            break

    approve_model(request_id)

    if user_id:
        try:
            await bot.send_message(
                user_id,
                f"✅ Вашу модель підтверджено:\n{brand} {model}"
            )
        except:
            pass

    await callback.message.edit_text("✅ Модель підтверджено")
    await callback.answer()


@router.callback_query(F.data.startswith("model_no_"))
async def reject_model_cb(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    model_requests = get_pending_model_requests()

    user_id = None
    brand = None
    model = None

    for r in model_requests:
        if r[0] == request_id:
            _, user_id, brand, model = r
            break

    reject_model(request_id)

    if user_id:
        try:
            await bot.send_message(
                user_id,
                f"❌ Вашу модель відхилено:\n{brand} {model}"
            )
        except:
            pass

    await callback.message.edit_text("❌ Модель відхилено")
    await callback.answer()


# ================= EDIT MODEL =================

@router.callback_query(F.data.startswith("model_edit_"))
async def edit_model_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        return

    request_id = int(callback.data.split("_")[-1])

    await state.update_data(request_id=request_id)
    await callback.message.answer("✏️ Введіть правильну назву моделі:")
    await state.set_state(EditModel.waiting_for_new_model)

    await callback.answer()


@router.message(EditModel.waiting_for_new_model)
async def edit_model_save(message: types.Message, state: FSMContext):
    new_model = message.text.strip().upper()

    data = await state.get_data()
    request_id = data.get("request_id")

    update_model_request(request_id, new_model)
    approve_model(request_id)

    await message.answer(f"✅ Модель виправлено та підтверджено: {new_model}")

    await state.clear()


# ================= ADD USER =================

@router.message(lambda m: m.text == "➕ Додати користувача")
async def add_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    await message.answer("Введіть ім'я користувача:")
    await state.set_state(AddUser.name)


@router.message(AddUser.name)
async def get_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Введіть посилання на сайт:")
    await state.set_state(AddUser.website)


@router.message(AddUser.website)
async def get_website(message: types.Message, state: FSMContext):
    await state.update_data(website=message.text.strip())
    await message.answer("Введіть номер телефону:")
    await state.set_state(AddUser.phone)


@router.message(AddUser.phone)
async def get_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())

    await message.answer(
        "Введіть моделі у форматі:\n\n"
        "Model: Audi\nA4\nA6\n\n"
        "Model: BMW\nE60\nF30"
    )

    await state.set_state(AddUser.models)


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
