from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message

from bot.services.roles import is_admin
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import (
    brand_request_kb,
    model_request_kb,
    verification_request_kb,
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
    approve_seller,
    reject_seller
)

from bot.database.repositories.user_repo import (
    get_visits,
    get_all_users,
    get_user_by_id,
    delete_user_full
)

from bot.database.repositories.seller_repo import get_seller_by_id
from bot.utils.cache import clear_brands_cache, clear_models_cache

router = Router()
CANCEL = KeyboardButton(text="❌ Скасувати")


# ================= ADMIN PANEL =================

@router.message(lambda m: m.text and m.text.startswith("⚙️"))
async def open_admin_panel(message: Message, state: FSMContext):
    await state.clear()

    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Немає доступу")
        return

    await message.answer("⚙️ Адмін панель", reply_markup=admin_kb)


# ================= USERS =================

@router.message(lambda m: m.text and m.text.startswith("👥"))
async def admin_users(message: Message, state: FSMContext):
    await state.clear()

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


# ================= VISITS =================

@router.message(lambda m: m.text and m.text.startswith("📊"))
async def admin_visits(message: Message, state: FSMContext):
    await state.clear()

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

    MAX = 4000
    for i in range(0, len(text), MAX):
        await message.answer(text[i:i+MAX])


# ================= REQUESTS =================

@router.message(lambda m: m.text and m.text.startswith("📋"))
async def show_requests(message: types.Message, state: FSMContext):
    await state.clear()

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
       # ================= BRAND APPROVE =================

@router.callback_query(F.data.startswith("admin:brand:ok:"))
async def approve_brand_handler(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])

    requests = await get_pending_brand_requests()

    request_data = next(
        (r for r in requests if r["id"] == request_id),
        None
    )

    if not request_data:
        await callback.answer("❌ Заявка не знайдена", show_alert=True)
        return

    await approve_brand(request_id)

    clear_brands_cache()

    seller = await get_seller_by_id(request_data["user_id"])

    if seller:
        try:
            await callback.bot.send_message(
                seller["telegram_id"],
                (
                    "✅ Ваш бренд погоджено модератором\n\n"
                    f"🏷 Бренд: {request_data['brand']}\n\n"
                    "Тепер ви можете додати авто у свій гараж."
                )
            )
        except Exception:
            pass

    await callback.message.edit_text(
        (
            "✅ Бренд погоджено\n\n"
            f"🏷 {request_data['brand']}"
        )
    )

    await callback.answer()


@router.callback_query(F.data.startswith("admin:brand:no:"))
async def reject_brand_handler(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])

    requests = await get_pending_brand_requests()

    request_data = next(
        (r for r in requests if r["id"] == request_id),
        None
    )

    if not request_data:
        await callback.answer("❌ Заявка не знайдена", show_alert=True)
        return

    await reject_brand(request_id)

    seller = await get_seller_by_id(request_data["user_id"])

    if seller:
        try:
            await callback.bot.send_message(
                seller["telegram_id"],
                (
                    "❌ Ваш бренд відхилено модератором\n\n"
                    f"🏷 Бренд: {request_data['brand']}"
                )
            )
        except Exception:
            pass

    await callback.message.edit_text(
        (
            "❌ Бренд відхилено\n\n"
            f"🏷 {request_data['brand']}"
        )
    )

    await callback.answer()


# ================= MODEL APPROVE =================

@router.callback_query(F.data.startswith("admin:model:ok:"))
async def approve_model_handler(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])

    requests = await get_pending_model_requests()

    request_data = next(
        (r for r in requests if r["id"] == request_id),
        None
    )

    if not request_data:
        await callback.answer("❌ Заявка не знайдена", show_alert=True)
        return

    await approve_model(request_id)

    clear_models_cache(request_data["brand"])

    seller = await get_seller_by_id(request_data["user_id"])

    if seller:
        try:
            await callback.bot.send_message(
                seller["telegram_id"],
                (
                    "✅ Вашу модель погоджено модератором\n\n"
                    f"🏷 Бренд: {request_data['brand']}\n"
                    f"🚗 Модель: {request_data['model']}\n\n"
                    "Тепер ви можете додати авто у свій гараж."
                )
            )
        except Exception:
            pass

    await callback.message.edit_text(
        (
            "✅ Модель погоджено\n\n"
            f"🏷 {request_data['brand']}\n"
            f"🚗 {request_data['model']}"
        )
    )

    await callback.answer()


@router.callback_query(F.data.startswith("admin:model:no:"))
async def reject_model_handler(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])

    requests = await get_pending_model_requests()

    request_data = next(
        (r for r in requests if r["id"] == request_id),
        None
    )

    if not request_data:
        await callback.answer("❌ Заявка не знайдена", show_alert=True)
        return

    await reject_model(request_id)

    seller = await get_seller_by_id(request_data["user_id"])

    if seller:
        try:
            await callback.bot.send_message(
                seller["telegram_id"],
                (
                    "❌ Вашу модель відхилено модератором\n\n"
                    f"🏷 Бренд: {request_data['brand']}\n"
                    f"🚗 Модель: {request_data['model']}"
                )
            )
        except Exception:
            pass

    await callback.message.edit_text(
        (
            "❌ Модель відхилено\n\n"
            f"🏷 {request_data['brand']}\n"
            f"🚗 {request_data['model']}"
        )
    )

    await callback.answer()
# ================= VERIFICATION =================

@router.callback_query(F.data.startswith("admin:verify:ok:"))
async def approve_verification(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])

    telegram_id = await approve_seller(request_id)

    if not telegram_id:
        await callback.answer("❌ Заявка не знайдена", show_alert=True)
        return

    if callback.message.caption:
        await callback.message.edit_caption("✅ Верифікацію підтверджено")
    else:
        await callback.message.edit_text("✅ Верифікацію підтверджено")

    await callback.bot.send_message(
        telegram_id,
        "✅ Ваш акаунт підтверджено\nТепер вам доступні всі функції продавця"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("admin:verify:no:"))
async def reject_verification(callback: CallbackQuery):
    request_id = int(callback.data.split(":")[-1])

    telegram_id = await reject_seller(request_id)

    if not telegram_id:
        await callback.answer("❌ Заявка не знайдена", show_alert=True)
        return

    if callback.message.caption:
        await callback.message.edit_caption("❌ Верифікацію відхилено")
    else:
        await callback.message.edit_text("❌ Верифікацію відхилено")

    await callback.bot.send_message(
        telegram_id,
        "❌ Верифікацію відхилено\nСпробуйте ще раз"
    )

    await callback.answer()
