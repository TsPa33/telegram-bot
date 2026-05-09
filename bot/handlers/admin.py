import secrets
import zlib
from datetime import datetime, timedelta

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message

from bot.services.roles import is_admin
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.seller_menu import site_menu_kb
from bot.keyboards.admin_inline import (
    brand_request_kb,
    model_request_kb,
    verification_request_kb,
    admin_users_kb,
    admin_user_actions_kb,
    admin_confirm_delete_kb,
    admin_demo_menu_kb,
    admin_demo_sites_kb,
    admin_demo_site_actions_kb,
    admin_demo_confirm_delete_kb,
)

from bot.states.admin_states import EditBrand, EditModel, DemoSiteStates

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
    reject_seller,
)

from bot.database.repositories.crm_repo import (
    create_admin_session,
    get_admin_by_telegram_id,
    log_admin_action,
)

from bot.database.repositories.user_repo import (
    get_visits,
    get_all_users,
    get_user_by_id,
    delete_user_full,
)

from bot.database.repositories.seller_repo import (
    get_seller_by_id,
    create_demo_seller,
)

from bot.database.repositories.site_repo import (
    create_site,
    get_demo_sites,
    get_site_by_id,
    subdomain_exists,
    soft_delete_demo_site,
)

from bot.services.demo_context import clear_demo_context, set_demo_context
from bot.services.site_config import get_default_site_config
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


# ================= CRM =================

@router.message(lambda m: m.text == "🧩 CRM")
async def open_crm(message: Message, state: FSMContext):
    await state.clear()

    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Немає доступу")
        return

    admin = await get_admin_by_telegram_id(message.from_user.id)

    if not admin or not admin["is_active"]:
        await message.answer("⛔ CRM доступ не налаштований")
        return

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    session = await create_admin_session(
        message.from_user.id,
        token,
        expires_at,
    )

    if not session:
        await message.answer("⛔ Не вдалося створити CRM сесію")
        return

    await log_admin_action(
        admin["id"],
        "crm_login_link_created",
        entity_type="admin_session",
        entity_id=str(session["id"]),
    )

    await message.answer(
        "🧩 CRM доступ дійсний 10 хвилин:\n"
        f"https://worker-production-e30f.up.railway.app/admin/crm/login?token={token}"
    )


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
        reply_markup=admin_users_kb(users),
    )


@router.callback_query(F.data == "admin:users")
async def admin_users_back(callback: CallbackQuery):
    users = await get_all_users()

    await callback.message.edit_text(
        "👥 Список користувачів:",
        reply_markup=admin_users_kb(users),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:user:"))
async def user_actions(callback: CallbackQuery):
    user_id = int(callback.data.split(":")[-1])

    await callback.message.edit_text(
        f"👤 Користувач ID: {user_id}",
        reply_markup=admin_user_actions_kb(user_id),
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
        reply_markup=admin_confirm_delete_kb(user_id),
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
        await message.answer(text[i:i + MAX])


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
                reply_markup=brand_request_kb(r["id"]),
            )

    if model_requests:
        for r in model_requests:
            await message.answer(
                f"🆕 Модель\n👤 {r['user_id']}\n🚗 {r['brand']} {r['model']}",
                reply_markup=model_request_kb(r["id"]),
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
        None,
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
                ),
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
        None,
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
                ),
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
        None,
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
                ),
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
        None,
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
                ),
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
        "✅ Ваш акаунт підтверджено\nТепер вам доступні всі функції продавця",
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
        "❌ Верифікацію відхилено\nСпробуйте ще раз",
    )

    await callback.answer()


# ================= DEMO SITES =================

@router.message(lambda m: m.text == "🌐 Демо сайти")
async def admin_demo_sites_menu(message: Message, state: FSMContext):
    await state.clear()

    if not await is_admin(message.from_user.id):
        await message.answer("⛔ Немає доступу")
        return

    await message.answer(
        "🌐 Демо сайти",
        reply_markup=admin_demo_menu_kb(),
    )


@router.callback_query(F.data == "admin:demo:menu")
async def admin_demo_sites_menu_callback(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "🌐 Демо сайти",
        reply_markup=admin_demo_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:demo:add")
async def admin_demo_add_start(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    await state.clear()
    await state.set_state(DemoSiteStates.title)
    await callback.message.answer(
        "➕ Додати демо сайт\n\n"
        "Введіть назву демо сайту.\n"
        "Наприклад: СТО, Шиномонтаж, Евакуатор"
    )
    await callback.answer()


@router.message(DemoSiteStates.title)
async def admin_demo_add_title(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Немає доступу")
        return

    title = (message.text or "").strip()[:100]
    if not title:
        await message.answer("Назва не може бути порожньою")
        return

    await state.update_data(demo_title=title)
    await state.set_state(DemoSiteStates.subdomain)
    await message.answer(
        "Введіть subdomain для демо сайту.\n\n"
        "Формат: demo-sto\n"
        "Приклади: demo-sto, demo-tire, demo-tow, demo-electric, demo-parts"
    )


@router.message(DemoSiteStates.subdomain)
async def admin_demo_add_subdomain(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Немає доступу")
        return

    data = await state.get_data()
    title = data.get("demo_title")
    subdomain = _normalize_demo_subdomain(message.text or "")

    if not title:
        await state.clear()
        await message.answer("Сесію створення втрачено. Спробуйте ще раз.")
        return

    if not subdomain:
        await message.answer(
            "❌ Невірний формат. Використайте тільки латиницю, цифри та дефіс: demo-sto"
        )
        return

    if not subdomain.startswith("demo-"):
        await message.answer("❌ Demo subdomain має починатися з demo-")
        return

    if await subdomain_exists(subdomain):
        await message.answer("❌ Такий subdomain вже існує")
        return

    seller = await create_demo_seller(
        telegram_id=_demo_telegram_id(subdomain),
        username=subdomain.replace("-", "_"),
        title=title,
    )

    config = get_default_site_config()
    config["header"]["title"] = title
    config["hero"]["title"] = title

    site = await create_site(
        seller_id=seller["id"],
        subdomain=subdomain,
        config=config,
    )

    await state.clear()
    await message.answer(
        "✅ Демо сайт створено\n\n"
        f"Назва: {title}\n"
        f"Subdomain: {site['subdomain']}\n"
        f"URL: https://worker-production-e30f.up.railway.app/site/{site['subdomain']}"
    )


@router.callback_query(F.data == "admin:demo:list")
async def admin_demo_list(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    sites = await get_demo_sites()
    if not sites:
        await callback.message.edit_text(
            "🌐 Демо сайти\n\nПоки немає демо сайтів.",
            reply_markup=admin_demo_menu_kb(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📋 Список демо сайтів",
        reply_markup=admin_demo_sites_kb(sites),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:demo:view:"))
async def admin_demo_view(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    site_id = int(callback.data.split(":")[-1])
    site = await get_site_by_id(site_id)

    if not site or not str(site["subdomain"]).startswith("demo-"):
        await callback.answer("Демо сайт не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        _demo_site_text(site),
        reply_markup=admin_demo_site_actions_kb(site),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:demo:edit:"))
async def admin_demo_edit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    site_id = int(callback.data.split(":")[-1])
    site = await get_site_by_id(site_id)

    if not site or not str(site["subdomain"]).startswith("demo-"):
        await callback.answer("Демо сайт не знайдено", show_alert=True)
        return

    await state.clear()
    await set_demo_context(
        state,
        seller_id=site["seller_id"],
        site_id=site["id"],
        subdomain=site["subdomain"],
    )

    await callback.message.answer(
        "✅ Demo edit mode увімкнено\n\n"
        f"Домен: {site['subdomain']}\n"
        f"Статус: {site.get('status', 'active')}",
        reply_markup=site_menu_kb(
            subdomain=site["subdomain"],
            is_active=(site.get("status", "active") == "active"),
            demo_mode=True,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:demo:delete:"))
async def admin_demo_delete(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    site_id = int(callback.data.split(":")[-1])
    site = await get_site_by_id(site_id)

    if not site or not str(site["subdomain"]).startswith("demo-"):
        await callback.answer("Демо сайт не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        "⚠️ Видалити demo сайт?\n\n"
        f"Subdomain: {site['subdomain']}\n"
        "Сайт буде приховано зі списку demo сайтів без видалення seller record.",
        reply_markup=admin_demo_confirm_delete_kb(site_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:demo:delete_confirm:"))
async def admin_demo_delete_confirm(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    site_id = int(callback.data.split(":")[-1])
    site = await get_site_by_id(site_id)

    if not site or not str(site["subdomain"]).startswith("demo-"):
        await callback.answer("Демо сайт не знайдено", show_alert=True)
        return

    deleted = await soft_delete_demo_site(site_id)

    if not deleted:
        await callback.answer("Не вдалося видалити demo сайт", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑 Демо сайт видалено\n\n"
        f"Subdomain: {site['subdomain']}",
        reply_markup=admin_demo_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "demo:exit")
async def demo_exit(callback: CallbackQuery, state: FSMContext):
    if not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Немає доступу", show_alert=True)
        return

    await clear_demo_context(state)
    await callback.message.answer("⬅️ Demo edit mode вимкнено", reply_markup=admin_kb)
    await callback.answer()


def _normalize_demo_subdomain(value: str) -> str | None:
    subdomain = value.strip().lower()
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"

    if not subdomain or any(char not in allowed for char in subdomain):
        return None

    if subdomain.startswith("-") or subdomain.endswith("-") or "--" in subdomain:
        return None

    if len(subdomain) > 63:
        return None

    return subdomain


def _demo_telegram_id(subdomain: str) -> int:
    return -int(zlib.crc32(subdomain.encode("utf-8")))


def _demo_site_text(site) -> str:
    config = site.get("config_draft") or {}
    title = ""

    if isinstance(config, dict):
        title = (config.get("header") or {}).get("title") or ""

    return (
        "🌐 Демо сайт\n\n"
        f"Назва: {title or '-'}\n"
        f"Subdomain: {site['subdomain']}\n"
        f"URL: https://worker-production-e30f.up.railway.app/site/{site['subdomain']}"
    )