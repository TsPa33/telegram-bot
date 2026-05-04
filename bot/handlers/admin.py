from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message

from bot.services.roles import is_admin
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import (
    brand_request_kb,
    model_request_kb,
    verification_request_kb,

    # NEW
    admin_users_kb,
    admin_user_actions_kb,
    admin_confirm_delete_kb
)

from bot.states.admin_states import EditBrand, EditModel

from bot.database.repositories.admin_repo import (
    get_pending_brand_requests,
    get_pending_model_requests,
    approve_brand,
    reject_brand,
    approve_model,
    reject_model,
    update_brand_request,
    update_model_request,
    get_verification_requests,
    approve_seller,
    reject_seller
)

# NEW
from bot.database.repositories.user_repo import (
    get_visits,
    get_all_users,
    get_user_by_id,
    delete_user_full
)

from bot.utils.cache import clear_brands_cache, clear_models_cache

router = Router()

CANCEL = KeyboardButton(text="❌ Скасувати")


# ================= ADMIN PANEL =================

@router.message(F.text == "⚙️ Адмін панель")
async def open_admin_panel(message: Message):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Немає доступу")
        return

    await message.answer(
        "⚙️ Адмін панель",
        reply_markup=admin_kb
    )


# ================= 👥 USERS =================

@router.message(F.text == "👥 Користувачі")
async def admin_users(message: Message):
    if not await is_admin(message.from_user.id):
        return

    users = await get_all_users()

    if not users:
        await message.answer("Немає користувачів")
        return

    await message.answer(
        "👥 Список користувачів:",
        reply_markup=admin_users_kb(users)
    )


@router.callback_query(F.data == "admin:users")
async def admin_users_back(callback: CallbackQuery):
    users = await get_all_users()

    await callback.message.edit_text(
        "👥 Список користувачів:",
        reply_markup=admin_users_kb(users)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:user:"))
async def user_actions(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[-1])

    await callback.message.edit_text(
        f"👤 Користувач ID: {user_id}",
        reply_markup=admin_user_actions_kb(user_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:view:"))
async def view_user(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[-1])

    user = await get_user_by_id(user_id)

    if not user:
        await callback.message.answer("Користувача не знайдено")
        await callback.answer()
        return

    text = (
        f"👤 ID: {user['id']}\n"
        f"📱 TG: {user['telegram_id']}\n"
        f"👤 Username: @{user['username'] or '-'}"
    )

    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete:"))
async def confirm_delete(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[-1])

    await callback.message.edit_text(
        f"⚠️ Видалити користувача {user_id}?",
        reply_markup=admin_confirm_delete_kb(user_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete_confirm:"))
async def delete_user_handler(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[-1])

    await delete_user_full(user_id)

    await callback.message.edit_text(f"❌ Користувач {user_id} видалений")
    await callback.answer()


# ================= 📊 VISITS =================

@router.message(F.text == "📊 Перегляди")
async def admin_visits(message: Message):
    if not await is_admin(message.from_user.id):
        return

    rows = await get_visits()

    if not rows:
        await message.answer("Немає даних")
        return

    text = ""
    current_date = None

    for row in rows:
        if row["date"] != current_date:
            text += f"\n📅 {row['date']}\n"
            current_date = row["date"]

        text += (
            f"ID: {row['telegram_id']}\n"
            f"Name: {row['name']}\n"
            f"Username: @{row['username'] or '-'}\n"
            f"Phone: {row['phone'] or '-'}\n"
            f"Role: {row['role']}\n\n"
        )

    await message.answer(text)


# ================= REQUESTS =================

@router.message(F.text.startswith("📋 Заявки"))
async def show_requests(message: types.Message):
    if not await is_admin(message.from_user.id):
        return

    brand_requests = await get_pending_brand_requests()
    model_requests = await get_pending_model_requests()

    if brand_requests:
        for r in brand_requests:
            await message.answer(
                f"🆕 Бренд\n👤 {r['user_id']}\n🏷 {r['brand']}",
                reply_markup=brand_request_kb(r["id"])
            )

    if model_requests:
        for r in model_requests:
            await message.answer(
                f"🆕 Модель\n👤 {r['user_id']}\n🚗 {r['brand']} {r['model']}",
                reply_markup=model_request_kb(r["id"])
            )

    if not brand_requests and not model_requests:
        await message.answer("✅ Немає заявок")


# ================= CALLBACK =================

@router.callback_query(F.data.regexp(r"^admin:(brand|model|verify):"))
async def handle_callbacks(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer()
        return

    _, entity, action, obj_id = parts

    try:
        obj_id = int(obj_id)
    except:
        await callback.answer()
        return

    if entity == "brand":
        if action == "ok":
            await approve_brand(obj_id)
            clear_brands_cache()
            await callback.message.edit_text("✅ Бренд підтверджено")

        elif action == "no":
            await reject_brand(obj_id)
            await callback.message.edit_text("❌ Бренд відхилено")

        elif action == "edit":
            await state.set_state(EditBrand.waiting_for_new_brand)
            await state.update_data(request_id=obj_id)
            await callback.message.answer("✏️ Введи новий бренд:")

    elif entity == "model":
        if action == "ok":
            await approve_model(obj_id)
            clear_models_cache()
            await callback.message.edit_text("✅ Модель підтверджено")

        elif action == "no":
            await reject_model(obj_id)
            await callback.message.edit_text("❌ Модель відхилено")

        elif action == "edit":
            await state.set_state(EditModel.waiting_for_new_model)
            await state.update_data(request_id=obj_id)
            await callback.message.answer("✏️ Введи нову модель:")

    elif entity == "verify":
        if action == "ok":
            telegram_id = await approve_seller(obj_id)

            if telegram_id:
                try:
                    await callback.bot.send_message(
                        chat_id=telegram_id,
                        text="✅ Твій акаунт верифіковано!"
                    )
                except:
                    pass

            await callback.message.answer("✅ Верифіковано")

        elif action == "no":
            telegram_id = await reject_seller(obj_id)

            if telegram_id:
                try:
                    await callback.bot.send_message(
                        chat_id=telegram_id,
                        text="❌ Верифікацію відхилено"
                    )
                except:
                    pass

            await callback.message.answer("❌ Відхилено")

    await callback.answer()


# ================= EDIT BRAND =================

@router.message(EditBrand.waiting_for_new_brand)
async def edit_brand_save(message: Message, state: FSMContext):
    new_brand = message.text.strip().title()

    data = await state.get_data()
    request_id = data.get("request_id")

    await update_brand_request(request_id, new_brand)
    await approve_brand(request_id)
    clear_brands_cache()

    await message.answer(f"✅ Бренд: {new_brand}")
    await state.clear()


# ================= EDIT MODEL =================

@router.message(EditModel.waiting_for_new_model)
async def edit_model_save(message: Message, state: FSMContext):
    new_model = message.text.strip().upper()

    data = await state.get_data()
    request_id = data.get("request_id")

    await update_model_request(request_id, new_model)
    await approve_model(request_id)
    clear_models_cache()

    await message.answer(f"✅ Модель: {new_model}")
    await state.clear()
