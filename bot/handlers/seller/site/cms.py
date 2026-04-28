import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.database.repositories.car_repo import (
    create_seller_car,
    delete_seller_car,
    get_cars_by_seller,
)
from bot.database.repositories.model_repo import get_model_id
from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.database.repositories.service_repo import (
    create_service,
    delete_service_by_seller,
    get_services_by_seller,
    update_service,
)
from bot.database.repositories.site_repo import get_site_by_seller, update_site_config
from bot.services.site_config import merge_with_default
from bot.states.seller_states import SellerSiteStates

router = Router()


def _parse_config(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return raw or {}


def _parse_service_payload(text: str):
    parts = [p.strip() for p in (text or "").split("|")]
    if len(parts) < 2:
        return None
    return {
        "title": parts[0],
        "description": parts[1],
        "price": parts[2] if len(parts) > 2 else "",
    }


def _parse_car_payload(text: str):
    parts = [p.strip() for p in (text or "").split("|")]
    if len(parts) < 4:
        return None
    return {
        "title": parts[0],
        "brand": parts[1],
        "model": parts[2],
        "description": parts[3],
        "price": parts[4] if len(parts) > 4 else "",
    }


async def _get_seller_site(callback_or_message):
    user = callback_or_message.from_user
    if not user:
        return None, None

    seller = await get_seller_by_telegram_id(user.id)
    if not seller:
        return None, None

    site = await get_site_by_seller(seller["id"])
    return seller, site


@router.callback_query(F.data == "site:services:menu")
async def services_menu(callback: CallbackQuery):
    await callback.answer("🛠 Послуги: Додати / Список / Вкл-Викл")


@router.callback_query(F.data == "site:services:add")
async def service_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_service_create)
    await callback.message.answer(
        "Надішліть: Назва|Опис|Ціна (ціна опціонально).\n"
        "Можна надіслати фото з підписом у такому форматі."
    )
    await callback.answer()


@router.message(SellerSiteStates.site_service_create, F.photo)
async def service_add_photo(message: Message, state: FSMContext):
    payload = _parse_service_payload(message.caption or "")
    if not payload or not payload["title"]:
        await message.answer("Формат: Назва|Опис|Ціна")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        return

    service_id = await create_service(
        seller_id=seller["id"],
        category="CMS",
        title=payload["title"],
        city="",
        address="",
        description=payload["description"],
        website=payload["price"] or None,
        photo_id=message.photo[-1].file_id,
    )

    if not service_id:
        await message.answer("Помилка створення послуги")
        return

    seller_site = await get_site_by_seller(seller["id"])
    if seller_site:
        config = merge_with_default(_parse_config(seller_site.get("config_draft")))
        services_cfg = config.setdefault("services", {})
        prices = services_cfg.setdefault("prices", {})
        prices[str(service_id)] = payload["price"]
        await update_site_config(seller_site["id"], config)

    await state.clear()
    await message.answer("✅ Послугу додано")


@router.message(SellerSiteStates.site_service_create)
async def service_add_text(message: Message, state: FSMContext):
    payload = _parse_service_payload(message.text or "")
    if not payload or not payload["title"]:
        await message.answer("Формат: Назва|Опис|Ціна")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        return

    service_id = await create_service(
        seller_id=seller["id"],
        category="CMS",
        title=payload["title"],
        city="",
        address="",
        description=payload["description"],
        website=payload["price"] or None,
        photo_id=None,
    )

    if not service_id:
        await message.answer("Помилка створення послуги")
        return

    seller_site = await get_site_by_seller(seller["id"])
    if seller_site:
        config = merge_with_default(_parse_config(seller_site.get("config_draft")))
        services_cfg = config.setdefault("services", {})
        prices = services_cfg.setdefault("prices", {})
        prices[str(service_id)] = payload["price"]
        await update_site_config(seller_site["id"], config)

    await state.clear()
    await message.answer("✅ Послугу додано")


@router.callback_query(F.data == "site:services:list")
async def services_list(callback: CallbackQuery):
    seller, _site = await _get_seller_site(callback)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    services = await get_services_by_seller(seller["id"])
    if not services:
        await callback.message.answer("Послуги відсутні")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=s["title"], callback_data=f"site:service:item:{s['id']}")]
            for s in services
        ]
    )
    await callback.message.answer("📋 Список послуг", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("site:service:item:"))
async def service_item(callback: CallbackQuery):
    service_id = int((callback.data or "").split(":")[-1])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"site:service:edit:{service_id}"),
                InlineKeyboardButton(text="❌ Видалити", callback_data=f"site:service:delete:{service_id}"),
            ]
        ]
    )
    await callback.message.answer(f"Послуга #{service_id}", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("site:service:edit:"))
async def service_edit_start(callback: CallbackQuery, state: FSMContext):
    service_id = int((callback.data or "").split(":")[-1])
    await state.update_data(service_edit_id=service_id)
    await state.set_state(SellerSiteStates.site_service_edit)
    await callback.message.answer("Введіть нові дані: Назва|Опис|Ціна")
    await callback.answer()


@router.message(SellerSiteStates.site_service_edit)
async def service_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    service_id = data.get("service_edit_id")
    payload = _parse_service_payload(message.text or "")

    if not service_id or not payload:
        await message.answer("Формат: Назва|Опис|Ціна")
        return

    await update_service(service_id, "title", payload["title"])
    await update_service(service_id, "description", payload["description"])

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if seller:
        seller_site = await get_site_by_seller(seller["id"])
        if seller_site:
            config = merge_with_default(_parse_config(seller_site.get("config_draft")))
            services_cfg = config.setdefault("services", {})
            prices = services_cfg.setdefault("prices", {})
            prices[str(service_id)] = payload["price"]
            await update_site_config(seller_site["id"], config)

    await state.clear()
    await message.answer("✅ Послугу оновлено")


@router.callback_query(F.data.startswith("site:service:delete:"))
async def service_delete(callback: CallbackQuery):
    service_id = int((callback.data or "").split(":")[-1])
    seller, seller_site = await _get_seller_site(callback)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    ok = await delete_service_by_seller(service_id, seller["id"])
    if ok and seller_site:
        config = merge_with_default(_parse_config(seller_site.get("config_draft")))
        services_cfg = config.setdefault("services", {})
        prices = services_cfg.setdefault("prices", {})
        prices.pop(str(service_id), None)
        await update_site_config(seller_site["id"], config)

    await callback.message.answer("✅ Послугу видалено" if ok else "Послугу не знайдено")
    await callback.answer()


@router.callback_query(F.data == "site:cars:menu")
async def cars_menu(callback: CallbackQuery):
    await callback.answer("🚗 Авто: Додати / Список / Видалити")


@router.callback_query(F.data == "site:cars:add")
async def cars_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_car_create)
    await callback.message.answer(
        "Надішліть: Заголовок|Бренд|Модель|Опис|Ціна (ціна опціонально).\n"
        "Можна надіслати фото з підписом у такому форматі."
    )
    await callback.answer()


async def _save_car(message: Message, state: FSMContext, payload: dict, photo_id: str | None):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        return

    model_id = await get_model_id(payload["brand"], payload["model"])
    if not model_id:
        await message.answer("Не вдалося визначити модель")
        return

    car = await create_seller_car(
        seller_id=seller["id"],
        model_id=model_id,
        description=payload["description"],
        photo_id=photo_id,
    )
    if not car:
        await message.answer("Помилка створення авто")
        return

    site = await get_site_by_seller(seller["id"])
    if site:
        config = merge_with_default(_parse_config(site.get("config_draft")))
        cars_cfg = config.setdefault("cars", {})
        titles = cars_cfg.setdefault("titles", {})
        prices = cars_cfg.setdefault("prices", {})
        car_id = str(car["id"])
        titles[car_id] = payload["title"]
        prices[car_id] = payload["price"]
        await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("✅ Авто додано")


@router.message(SellerSiteStates.site_car_create, F.photo)
async def cars_add_photo(message: Message, state: FSMContext):
    payload = _parse_car_payload(message.caption or "")
    if not payload:
        await message.answer("Формат: Заголовок|Бренд|Модель|Опис|Ціна")
        return
    await _save_car(message, state, payload, message.photo[-1].file_id)


@router.message(SellerSiteStates.site_car_create)
async def cars_add_text(message: Message, state: FSMContext):
    payload = _parse_car_payload(message.text or "")
    if not payload:
        await message.answer("Формат: Заголовок|Бренд|Модель|Опис|Ціна")
        return
    await _save_car(message, state, payload, None)


@router.callback_query(F.data == "site:cars:list")
async def cars_list(callback: CallbackQuery):
    seller, _site = await _get_seller_site(callback)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    cars = await get_cars_by_seller(seller["id"])
    if not cars:
        await callback.message.answer("Авто відсутні")
        await callback.answer()
        return

    text = "\n".join([f"#{c['id']} {c.get('brand', '')} {c.get('model', '')}" for c in cars])
    await callback.message.answer(f"📋 Список авто\n{text}")
    await callback.answer()


@router.callback_query(F.data == "site:cars:delete")
async def cars_delete_menu(callback: CallbackQuery):
    seller, _site = await _get_seller_site(callback)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    cars = await get_cars_by_seller(seller["id"])
    if not cars:
        await callback.message.answer("Авто відсутні")
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"❌ {c.get('brand', '')} {c.get('model', '')}",
                    callback_data=f"site:car:delete:{c['id']}",
                )
            ]
            for c in cars
        ]
    )
    await callback.message.answer("Оберіть авто для видалення", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("site:car:delete:"))
async def car_delete(callback: CallbackQuery):
    car_id = int((callback.data or "").split(":")[-1])
    seller, site = await _get_seller_site(callback)
    if not seller:
        await callback.answer("Продавця не знайдено", show_alert=True)
        return

    ok = await delete_seller_car(car_id, seller["id"])
    if ok and site:
        config = merge_with_default(_parse_config(site.get("config_draft")))
        cars_cfg = config.setdefault("cars", {})
        titles = cars_cfg.setdefault("titles", {})
        prices = cars_cfg.setdefault("prices", {})
        titles.pop(str(car_id), None)
        prices.pop(str(car_id), None)
        await update_site_config(site["id"], config)

    await callback.message.answer("✅ Авто видалено" if ok else "Авто не знайдено")
    await callback.answer()


@router.callback_query(F.data == "site:contacts:menu")
async def contacts_menu(callback: CallbackQuery):
    await callback.answer("📞 Контакти: Телефон / Адреса / Карта")


@router.callback_query(F.data == "site:contacts:phone")
async def contacts_phone_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_phone)
    await callback.message.answer("Введіть номер телефону")
    await callback.answer()


@router.callback_query(F.data == "site:contacts:address")
async def contacts_address_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_address)
    await callback.message.answer("Введіть адресу")
    await callback.answer()


@router.callback_query(F.data == "site:contacts:map")
async def contacts_map_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SellerSiteStates.site_contact_map)
    await callback.message.answer("Введіть iframe embed для карти")
    await callback.answer()


async def _update_contact_field(message: Message, state: FSMContext, field: str, value: str):
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        await state.clear()
        return

    config = merge_with_default(_parse_config(site.get("config_draft")))
    contacts = config.setdefault("contacts", {})
    contacts[field] = value.strip()

    await update_site_config(site["id"], config)
    await state.clear()


@router.message(SellerSiteStates.site_contact_phone)
async def contacts_phone_save(message: Message, state: FSMContext):
    await _update_contact_field(message, state, "phone", message.text or "")
    await message.answer("✅ Телефон оновлено")


@router.message(SellerSiteStates.site_contact_address)
async def contacts_address_save(message: Message, state: FSMContext):
    await _update_contact_field(message, state, "address", message.text or "")
    await message.answer("✅ Адресу оновлено")


@router.message(SellerSiteStates.site_contact_map)
async def contacts_map_save(message: Message, state: FSMContext):
    await _update_contact_field(message, state, "map_embed", message.text or "")
    await message.answer("✅ Карту оновлено")
