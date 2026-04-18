from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message

from bot.config import ADMINS
from bot.keyboards.admin_kb import admin_kb
from bot.keyboards.admin_inline import (
    brand_request_kb,
    model_request_kb,
    verification_request_kb
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

from bot.utils.cache import clear_brands_cache, clear_models_cache

from bot.services.import_service import (
    parse_seller_file,
    save_parsed_data
)

router = Router()

CANCEL = KeyboardButton(text="❌ Скасувати")


# ================= HELPERS =================

def is_admin(user_id: int):
    return user_id in ADMINS


def is_command(message: types.Message):
    return message.text and message.text.startswith("/")


async def cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Дію скасовано", reply_markup=admin_kb)


# ================= ADMIN PANEL =================

@router.message(F.text == "⚙️ Адмін панель")
async def open_admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("⚙️ Адмін панель", reply_markup=admin_kb)


# ================= REQUESTS =================

@router.message(F.text.startswith("📋 Заявки"))
async def show_requests(message: types.Message):
    if not is_admin(message.from_user.id):
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


# ================= VERIFICATION =================

@router.message(F.text.in_(["🔐 Верифікації", "🔐 Верифікація продавців"]))
async def show_verifications(message: Message):
    if not is_admin(message.from_user.id):
        return

    requests = await get_verification_requests()

    if not requests:
        await message.answer("✅ Немає заявок")
        return

    for seller in requests:
        photo = seller.get("passport_photo_id")

        if not photo:
            await message.answer(
                f"⚠️ Немає фото\n🆔 Request ID: {seller['id']}"
            )
            continue

        await message.answer_photo(
            photo=photo,
            caption=f"🆔 Request ID: {seller['id']}",
            reply_markup=verification_request_kb(seller["id"])
        )


# ================= CALLBACK HANDLER =================

@router.callback_query(F.data.regexp(r"^(brand|model|verify):"))
async def handle_callbacks(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    parts = callback.data.split(":")

    if len(parts) != 3:
        await callback.answer()
        return

    entity, action, obj_id = parts

    try:
        obj_id = int(obj_id)
    except:
        await callback.answer()
        return

    # ===== BRAND =====
    if entity == "brand":
        if action == "ok":
            await approve_brand(obj_id)
            await clear_brands_cache()
            await callback.message.edit_text("✅ Бренд підтверджено")

        elif action == "no":
            await reject_brand(obj_id)
            await callback.message.edit_text("❌ Бренд відхилено")

        elif action == "edit":
            await state.set_state(EditBrand.waiting_for_new_brand)
            await state.update_data(request_id=obj_id)
            await callback.message.answer("✏️ Введи новий бренд:")

    # ===== MODEL =====
    elif entity == "model":
        if action == "ok":
            await approve_model(obj_id)
            await clear_models_cache()
            await callback.message.edit_text("✅ Модель підтверджено")

        elif action == "no":
            await reject_model(obj_id)
            await callback.message.edit_text("❌ Модель відхилено")

        elif action == "edit":
            await state.set_state(EditModel.waiting_for_new_model)
            await state.update_data(request_id=obj_id)
            await callback.message.answer("✏️ Введи нову модель:")

    # ===== VERIFY =====
    elif entity == "verify":
        if action == "ok":
            telegram_id = await approve_seller(obj_id)

            if telegram_id:
                try:
                    await callback.bot.send_message(
                        chat_id=telegram_id,
                        text="✅ Твій акаунт верифіковано!\n\nТепер ти можеш додавати авто 🚀"
                    )
                except:
                    pass

            try:
                await callback.message.edit_caption("✅ Верифіковано")
            except:
                await callback.message.answer("✅ Верифіковано")

        elif action == "no":
            telegram_id = await reject_seller(obj_id)

            if telegram_id:
                try:
                    await callback.bot.send_message(
                        chat_id=telegram_id,
                        text="❌ Верифікацію відхилено\n\nСпробуй ще раз"
                    )
                except:
                    pass

            try:
                await callback.message.edit_caption("❌ Відхилено")
            except:
                await callback.message.answer("❌ Відхилено")

    await callback.answer()


# ================= EDIT BRAND =================

@router.message(EditBrand.waiting_for_new_brand)
async def edit_brand_save(message: types.Message, state: FSMContext):
    if is_command(message):
        await cancel(message, state)
        return

    new_brand = message.text.strip().title()

    data = await state.get_data()
    request_id = data.get("request_id")

    await update_brand_request(request_id, new_brand)
    await approve_brand(request_id)

    await message.answer(f"✅ Бренд: {new_brand}")
    await state.clear()


# ================= EDIT MODEL =================

@router.message(EditModel.waiting_for_new_model)
async def edit_model_save(message: types.Message, state: FSMContext):
    if is_command(message):
        await cancel(message, state)
        return

    new_model = message.text.strip().upper()

    data = await state.get_data()
    request_id = data.get("request_id")

    await update_model_request(request_id, new_model)
    await approve_model(request_id)

    await message.answer(f"✅ Модель: {new_model}")
    await state.clear()


# ================= FILE IMPORT =================

@router.message(F.document)
async def upload_sellers_file(message: Message):
    if not is_admin(message.from_user.id):
        return

    document = message.document

    if not document or not document.file_name.endswith(".txt"):
        await message.answer("❌ Тільки .txt")
        return

    try:
        file = await message.bot.get_file(document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)

        text = file_bytes.read().decode("utf-8")

        rows = await parse_seller_file(text)

        if not rows:
            await message.answer("❌ Невірний формат")
            return

        await save_parsed_data(rows)

        await message.answer(f"✅ Імпорт: {len(rows)} записів")

    except Exception as e:
        await message.answer("❌ Помилка імпорту")
        print(e)
