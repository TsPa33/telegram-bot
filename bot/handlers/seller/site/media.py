import json
import os

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from bot.states.seller_states import SellerSiteStates
from bot.database.repositories.site_repo import (
    get_site_by_seller,
    update_product_image,
    update_site_config,
)
from bot.database.repositories.service_repo import (
    clear_service_photo,
    get_service_by_seller,
    get_services_by_seller,
    update_service_photo,
)
from bot.services.site_config import merge_with_default
from bot.services.demo_context import clear_preserving_demo_context, resolve_active_seller
from bot.services.storage import upload_image

router = Router()


# ================= HELPERS =================

def safe_config(raw):
    if not raw:
        return {}

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}

    return dict(raw)


def _active_config(site: dict) -> dict:
    return merge_with_default(
        safe_config(site.get("config_draft"))
        or safe_config(site.get("config_live"))
    )


def _product_items(site: dict) -> list[dict]:
    config = _active_config(site)
    products = config.get("products") or {}
    items = products.get("items") or []

    if not isinstance(items, list):
        return []

    return [item for item in items if isinstance(item, dict)]


def _find_product(site: dict, product_id: str) -> dict | None:
    for product in _product_items(site):
        if str(product.get("id")) == str(product_id):
            return product

    return None


def _trim(text: str, limit: int = 48) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}…"


def products_media_list_kb(products: list[dict]) -> InlineKeyboardMarkup:
    rows = []

    for product in products:
        product_id = product.get("id")
        if not product_id:
            continue

        title = _trim(product.get("title") or "Без назви", 34)
        category = _trim(product.get("category") or "Товар", 18)
        rows.append([
            InlineKeyboardButton(
                text=f"{category} — {title}",
                callback_data=f"site:products:media:item:{product_id}",
            )
        ])

    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="site:media:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_media_item_kb(product_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Змінити фото", callback_data=f"site:products:media:set:{product_id}")],
        [InlineKeyboardButton(text="🗑 Видалити фото", callback_data=f"site:products:media:delete:{product_id}")],
        [InlineKeyboardButton(text="⬅ Назад до товарів", callback_data="site:products:media:list")],
    ])


def services_media_list_kb(services: list[dict]) -> InlineKeyboardMarkup:
    rows = []

    for service in services:
        service_id = service.get("id")
        if not service_id:
            continue

        title = _trim(service.get("title") or "Без назви", 34)
        category = _trim(service.get("category") or "Послуга", 18)
        rows.append([
            InlineKeyboardButton(
                text=f"{category} — {title}",
                callback_data=f"site:services:media:item:{service_id}",
            )
        ])

    rows.append([InlineKeyboardButton(text="⬅ Назад", callback_data="site:media:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_media_item_kb(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Змінити фото", callback_data=f"site:services:media:set:{service_id}")],
        [InlineKeyboardButton(text="🗑 Видалити фото", callback_data=f"site:services:media:delete:{service_id}")],
        [InlineKeyboardButton(text="⬅ Назад до послуг", callback_data="site:services:media:list")],
    ])


async def _resolve_site(message_or_callback: Message | CallbackQuery, state: FSMContext):
    seller = await resolve_active_seller(message_or_callback, state)

    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])
    return seller, site


async def _download_incoming_image(message: Message) -> str | None:
    file_path = None

    if message.document:
        document = message.document

        if not document.mime_type or not document.mime_type.startswith("image/"):
            await message.answer("Завантажте зображення як файл (PNG/JPG) ❌")
            return None

        file = await message.bot.get_file(document.file_id)
        file_path = document.file_name or f"{document.file_id}.png"
        await message.bot.download_file(file.file_path, file_path)
        return file_path

    if message.photo:
        await message.answer("⚠️ Фото стискається Telegram. Краще надсилати як файл для максимальної якості.")
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_path = f"{photo.file_id}.jpg"
        await message.bot.download_file(file.file_path, file_path)
        return file_path

    await message.answer("Надішліть зображення ❌")
    return None


async def _upload_message_image(message: Message) -> str | None:
    file_path = await _download_incoming_image(message)

    if not file_path:
        return None

    try:
        image_url = await upload_image(file_path)
    finally:
        try:
            os.remove(file_path)
        except Exception:
            pass

    if not image_url or not isinstance(image_url, str):
        await message.answer("Помилка завантаження зображення ❌")
        return None

    return image_url


# ================= PRODUCTS MEDIA =================

@router.callback_query(F.data == "site:products:media:list")
async def list_product_media(callback: CallbackQuery, state: FSMContext):
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    products = _product_items(site)

    if not products:
        await callback.message.edit_text(
            "❌ Товари не знайдено",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅ Назад", callback_data="site:media:menu")
            ]]),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "Оберіть товар для редагування фото:",
        reply_markup=products_media_list_kb(products),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:products:media:item:"))
async def show_product_media(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.removeprefix("site:products:media:item:")
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    product = _find_product(site, product_id)

    if not product:
        await callback.answer("❌ Товар не знайдено", show_alert=True)
        return

    status = "✅ Фото встановлено" if product.get("image") else "❌ Фото відсутнє"
    await callback.message.edit_text(
        "🖼 Фото товару\n\n"
        f"Назва: {product.get('title') or 'Без назви'}\n"
        f"Категорія: {product.get('category') or '—'}\n"
        f"Статус: {status}",
        reply_markup=product_media_item_kb(product_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:products:media:set:"))
async def set_product_media(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.removeprefix("site:products:media:set:")
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    product = _find_product(site, product_id)

    if not product:
        await callback.answer("❌ Товар не знайдено", show_alert=True)
        return

    await state.set_state(SellerSiteStates.site_product_photo)
    await state.update_data(product_id=product_id)

    await callback.message.answer(
        f"Надішліть фото для товару: {product.get('title') or 'Без назви'}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:products:media:delete:"))
async def delete_product_media(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.removeprefix("site:products:media:delete:")
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    product = _find_product(site, product_id)

    if not product:
        await callback.answer("❌ Товар не знайдено", show_alert=True)
        return

    updated = await update_product_image(site["id"], seller["id"], product_id, "")

    if not updated:
        await callback.answer("❌ Товар не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑 Фото товару видалено\n\n"
        f"Назва: {product.get('title') or 'Без назви'}",
        reply_markup=product_media_item_kb(product_id),
    )
    await callback.answer("🗑 Фото товару видалено")


@router.message(StateFilter(SellerSiteStates.site_product_photo), F.photo | F.document)
async def save_product_media(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")

    seller, site = await _resolve_site(message, state)

    if not seller:
        await clear_preserving_demo_context(state)
        await message.answer("Продавця не знайдено ❌")
        return

    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("Сайт не знайдено ❌")
        return

    product = _find_product(site, product_id)

    if not product:
        await clear_preserving_demo_context(state)
        await message.answer("❌ Товар не знайдено")
        return

    image_url = await _upload_message_image(message)

    if not image_url:
        await clear_preserving_demo_context(state)
        return

    updated = await update_product_image(site["id"], seller["id"], product_id, image_url)
    await clear_preserving_demo_context(state)

    if not updated:
        await message.answer("❌ Товар не знайдено")
        return

    await message.answer(
        "✅ Фото товару оновлено\n\n"
        "Зміни збережено в сайті."
    )


@router.message(StateFilter(SellerSiteStates.site_product_photo))
async def invalid_product_media(message: Message):
    await message.answer("Надішліть фото для товару або зображення як файл (PNG/JPG) ❌")


# ================= SERVICES MEDIA =================

@router.callback_query(F.data == "site:services:media:list")
async def list_service_media(callback: CallbackQuery, state: FSMContext):
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    services = [dict(service) for service in await get_services_by_seller(seller["id"])]

    if not services:
        await callback.message.edit_text(
            "❌ Послуги не знайдено",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅ Назад", callback_data="site:media:menu")
            ]]),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "Оберіть послугу для редагування фото:",
        reply_markup=services_media_list_kb(services),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:services:media:item:"))
async def show_service_media(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.removeprefix("site:services:media:item:"))
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    service = await get_service_by_seller(service_id, seller["id"])

    if not service:
        await callback.answer("❌ Послугу не знайдено", show_alert=True)
        return

    status = "✅ Фото встановлено" if service.get("photo_id") else "❌ Фото відсутнє"
    await callback.message.edit_text(
        "🛠 Фото послуги\n\n"
        f"Назва: {service.get('title') or 'Без назви'}\n"
        f"Категорія: {service.get('category') or '—'}\n"
        f"Статус: {status}",
        reply_markup=service_media_item_kb(service_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:services:media:set:"))
async def set_service_media(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.removeprefix("site:services:media:set:"))
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    service = await get_service_by_seller(service_id, seller["id"])

    if not service:
        await callback.answer("❌ Послугу не знайдено", show_alert=True)
        return

    await state.set_state(SellerSiteStates.site_service_photo)
    await state.update_data(service_id=service_id)

    await callback.message.answer(
        f"Надішліть фото для послуги: {service.get('title') or 'Без назви'}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site:services:media:delete:"))
async def delete_service_media(callback: CallbackQuery, state: FSMContext):
    service_id = int(callback.data.removeprefix("site:services:media:delete:"))
    seller, site = await _resolve_site(callback, state)

    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    if not site:
        await callback.answer("Сайт не знайдено", show_alert=True)
        return

    service = await get_service_by_seller(service_id, seller["id"])

    if not service:
        await callback.answer("❌ Послугу не знайдено", show_alert=True)
        return

    updated = await clear_service_photo(service_id, seller["id"])

    if not updated:
        await callback.answer("❌ Послугу не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑 Фото послуги видалено\n\n"
        f"Назва: {service.get('title') or 'Без назви'}",
        reply_markup=service_media_item_kb(service_id),
    )
    await callback.answer("🗑 Фото послуги видалено")


@router.message(StateFilter(SellerSiteStates.site_service_photo), F.photo | F.document)
async def save_service_media(message: Message, state: FSMContext):
    data = await state.get_data()
    service_id = data.get("service_id")

    seller, site = await _resolve_site(message, state)

    if not seller:
        await clear_preserving_demo_context(state)
        await message.answer("Продавця не знайдено ❌")
        return

    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("Сайт не знайдено ❌")
        return

    service = await get_service_by_seller(int(service_id), seller["id"])

    if not service:
        await clear_preserving_demo_context(state)
        await message.answer("❌ Послугу не знайдено")
        return

    image_url = await _upload_message_image(message)

    if not image_url:
        await clear_preserving_demo_context(state)
        return

    updated = await update_service_photo(int(service_id), seller["id"], image_url)
    await clear_preserving_demo_context(state)

    if not updated:
        await message.answer("❌ Послугу не знайдено")
        return

    await message.answer("✅ Фото послуги оновлено")


@router.message(StateFilter(SellerSiteStates.site_service_photo))
async def invalid_service_media(message: Message):
    await message.answer("Надішліть фото для послуги або зображення як файл (PNG/JPG) ❌")


# ================= MEDIA HANDLER =================

@router.message(
    StateFilter(SellerSiteStates.site_banner, SellerSiteStates.site_logo),
    F.photo | F.document
)
async def handle_media(message: Message, state: FSMContext):
    current_state = await state.get_state()

    seller = await resolve_active_seller(message, state)

    if not seller:
        await clear_preserving_demo_context(state)
        await message.answer("Продавця не знайдено ❌")
        return

    site = await get_site_by_seller(seller["id"])

    if not site:
        await clear_preserving_demo_context(state)
        await message.answer("Сайт не знайдено ❌")
        return

    config = merge_with_default(safe_config(site.get("config_draft")))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])
    config.setdefault("header", {})

    image_url = await _upload_message_image(message)

    if not image_url:
        await clear_preserving_demo_context(state)
        return

    # ================= LOGIC =================

    if current_state == SellerSiteStates.site_banner.state:
        config["hero"]["banners"].append(image_url)
        await message.answer("Банер додано ✅")

    elif current_state == SellerSiteStates.site_logo.state:
        config["header"]["logo"] = image_url
        await message.answer("Лого збережено ✅")

    await update_site_config(site["id"], config)
    await clear_preserving_demo_context(state)
