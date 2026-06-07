from decimal import Decimal, InvalidOperation
import re

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from bot.states.seller_states import SellerPartStates
from bot.database.repositories.seller_repo import get_seller_by_telegram_id
from bot.services.seller_access import get_verified_seller_or_warn
from bot.database.repositories.part_repo import (
    get_car_part_categories,
    get_parts_by_car_and_category,
    get_part_by_id,
    update_part_status,
    update_part_price,
    update_part_photo,
    update_part_description,
    get_seller_parts,
    seller_owns_car,
)
from bot.keyboards.parts_inline import (
    CATEGORY_SLUG_TO_NAME,
    CATEGORY_NAME_TO_SLUG,
    part_categories_kb,
    part_list_kb,
    part_card_kb,
)

router = Router()


def _part_text(part: dict) -> str:
    status = part.get("status", "draft").capitalize()
    return (
        f"🔧 {part['name']}\n"
        f"Vehicle: {part.get('brand') or '-'} {part.get('model') or '-'}\n"
        f"Category: {part['category']}\n\n"
        f"Status: {status}\n"
        f"Price: {part.get('price') if part.get('price') is not None else 'not specified'}\n"
        f"Photo: {'present' if part.get('photo_id') else 'missing'}\n"
        f"Description: {'present' if part.get('description') else 'missing'}\n\n"
        f"Visible on website: {'yes' if part.get('status') == 'available' else 'no'}"
    )


async def _resolve_seller(callback: CallbackQuery):
    seller = await get_seller_by_telegram_id(callback.from_user.id)
    if not seller:
        await callback.message.answer("❌ Seller profile not found")
        return None
    return seller


@router.callback_query(F.data.startswith("part:car:"))
async def part_car(callback: CallbackQuery):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    car_id = int(callback.data.split(":")[2])
    if not await seller_owns_car(seller["id"], car_id):
        await callback.message.answer("❌ Access denied")
        return

    categories = [dict(r) for r in await get_car_part_categories(car_id)]
    if not categories:
        await callback.message.answer("No parts generated for this vehicle.")
        return

    await callback.message.answer("🔧 Part categories:", reply_markup=part_categories_kb(car_id, categories))


@router.callback_query(F.data.startswith("part:cat:"))
async def part_category(callback: CallbackQuery):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    _, _, car_id_text, slug = callback.data.split(":", 3)
    car_id = int(car_id_text)

    if not await seller_owns_car(seller["id"], car_id):
        await callback.message.answer("❌ Access denied")
        return

    category = CATEGORY_SLUG_TO_NAME.get(slug)
    if not category:
        await callback.message.answer("❌ Access denied")
        return

    parts = [dict(r) for r in await get_parts_by_car_and_category(car_id, category)]
    await callback.message.answer(f"{category} parts:", reply_markup=part_list_kb(car_id, slug, parts))


@router.callback_query(F.data.startswith("part:view:"))
async def part_view(callback: CallbackQuery):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    part = await get_part_by_id(int(callback.data.split(":")[2]))
    if not part or part.get("seller_id") != seller["id"]:
        await callback.message.answer("❌ Access denied")
        return

    slug = CATEGORY_NAME_TO_SLUG.get(part["category"], "body")
    await callback.message.answer(_part_text(part), reply_markup=part_card_kb(part["id"], part["car_id"], slug))


@router.callback_query(
    F.data.startswith("part:available:")
    | F.data.startswith("part:draft:")
    | F.data.startswith("part:sold:")
    | F.data.startswith("part:hidden:")
)
async def part_set_status(callback: CallbackQuery):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    _, action, part_id_text = callback.data.split(":")
    part_id = int(part_id_text)
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != seller["id"]:
        await callback.message.answer("❌ Access denied")
        return

    ok = await update_part_status(part_id, seller["id"], action)
    await callback.message.answer("✅ Updated" if ok else "❌ Access denied")


@router.callback_query(F.data.startswith("part:price:"))
async def part_price_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    part_id = int(callback.data.split(":")[2])
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != seller["id"]:
        await callback.message.answer("❌ Access denied")
        return

    await state.set_state(SellerPartStates.waiting_price)
    await state.update_data(part_id=part_id)
    await callback.message.answer("Send price, e.g. 2500 or 2 500 usd")


@router.message(SellerPartStates.waiting_price)
async def part_price_save(message: Message, state: FSMContext):
    data = await state.get_data()
    part_id = data.get("part_id")
    if not part_id:
        await state.clear()
        await message.answer("❌ Session expired. Please open the part again.")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        await message.answer("❌ Seller profile not found")
        return

    part = await get_part_by_id(int(part_id))
    if not part or part.get("seller_id") != seller["id"]:
        await state.clear()
        await message.answer("❌ Access denied")
        return

    raw = re.sub(r"[^\d.,]", "", message.text or "").replace(" ", "").replace(",", ".")
    try:
        price = Decimal(raw)
    except (InvalidOperation, ValueError):
        await message.answer("Invalid price. Example: 2500")
        return

    await update_part_price(int(part_id), seller["id"], price)
    await state.clear()
    await message.answer("✅ Price updated")


@router.callback_query(F.data.startswith("part:photo:"))
async def part_photo_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    part_id = int(callback.data.split(":")[2])
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != seller["id"]:
        await callback.message.answer("❌ Access denied")
        return

    await state.set_state(SellerPartStates.waiting_photo)
    await state.update_data(part_id=part_id)
    await callback.message.answer("Send part photo")


@router.message(SellerPartStates.waiting_photo, F.photo)
async def part_photo_save(message: Message, state: FSMContext):
    data = await state.get_data()
    part_id = data.get("part_id")
    if not part_id:
        await state.clear()
        await message.answer("❌ Session expired. Please open the part again.")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        await message.answer("❌ Seller profile not found")
        return

    part = await get_part_by_id(int(part_id))
    if not part or part.get("seller_id") != seller["id"]:
        await state.clear()
        await message.answer("❌ Access denied")
        return

    await update_part_photo(int(part_id), seller["id"], message.photo[-1].file_id)
    await state.clear()
    await message.answer("✅ Photo updated")


@router.callback_query(F.data.startswith("part:desc:"))
async def part_desc_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    seller = await _resolve_seller(callback)
    if not seller:
        return

    part_id = int(callback.data.split(":")[2])
    part = await get_part_by_id(part_id)
    if not part or part.get("seller_id") != seller["id"]:
        await callback.message.answer("❌ Access denied")
        return

    await state.set_state(SellerPartStates.waiting_description)
    await state.update_data(part_id=part_id)
    await callback.message.answer("Send description (up to 1000 chars)")


@router.message(SellerPartStates.waiting_description)
async def part_desc_save(message: Message, state: FSMContext):
    data = await state.get_data()
    part_id = data.get("part_id")
    if not part_id:
        await state.clear()
        await message.answer("❌ Session expired. Please open the part again.")
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await state.clear()
        await message.answer("❌ Seller profile not found")
        return

    part = await get_part_by_id(int(part_id))
    if not part or part.get("seller_id") != seller["id"]:
        await state.clear()
        await message.answer("❌ Access denied")
        return

    if len(message.text or "") > 1000:
        await message.answer("Description too long (max 1000).")
        return

    await update_part_description(int(part_id), seller["id"], message.text or "")
    await state.clear()
    await message.answer("✅ Description updated")


@router.message(F.text == "🔧 My Parts")
async def my_parts(message: Message):
    if not await get_verified_seller_or_warn(message):
        return
    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        await message.answer("❌ Seller profile not found")
        return

    parts = [dict(p) for p in await get_seller_parts(seller["id"], limit=20)]
    if not parts:
        await message.answer("🔧 My Parts\n\nNo parts yet.")
        return

    lines = [f"- {p.get('brand','-')} {p.get('model','-')} | {p['name']} | {p['status']}" for p in parts]
    await message.answer("🔧 My Parts (showing first 20)\n\n" + "\n".join(lines))
