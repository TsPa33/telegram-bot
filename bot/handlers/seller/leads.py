import logging
from decimal import Decimal, InvalidOperation
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.base import fetchrow
from bot.database.repositories.seller_lead_repo import (
    cancel_seller_lead_notifications,
    create_seller_offer,
    ensure_buyer_offer_created_event,
    get_buyer_offer_notification_context,
    get_matching_seller_lead,
    get_seller_marketplace_profile,
    get_seller_specialization_tags,
    list_matching_seller_leads,
    mark_marketplace_notification_event,
    mark_seller_lead_action,
    touch_request_matched,
)
from bot.keyboards.buyer_requests_inline import buyer_offer_created_notification_kb
from bot.keyboards.seller_leads import (
    seller_lead_actions_kb,
    seller_lead_back_kb,
    seller_lead_declined_kb,
    seller_leads_inbox_kb,
    seller_offer_skip_step_kb,
)
from bot.services.seller_lead_matching import score_seller_lead
from bot.services.telegram_sender import send_message_to_buyer
from bot.states.seller_states import SellerLeadOfferStates

router = Router()
logger = logging.getLogger(__name__)

URGENCY_LABELS = {
    "today": "🔥 Терміново",
    "soon": "⚡ Найближчим часом",
    "week": "📅 До тижня",
    "flexible": "🕊 Гнучко",
}
STATUS_LABELS = {
    "pending": "🆕 Нова",
    "active": "🟢 Активна",
    "matched": "🤝 Є пропозиції",
    "closed": "✅ Закрита",
}


def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def _lead_title(lead: dict) -> str:
    description = (lead.get("description") or "").strip()
    for line in description.splitlines():
        line = line.strip()
        if line.startswith("Запит:") or line.startswith("Потрібно:"):
            title = line.split(":", 1)[1].strip()
            if title:
                return title[:120]
    return " ".join(
        part for part in [lead.get("brand"), lead.get("model"), lead.get("category")] if part
    ).strip() or lead.get("category") or "Автомобільна заявка"


def _has_photos(lead: dict) -> bool:
    photos = lead.get("photos")
    if not photos:
        return False
    if isinstance(photos, list):
        return bool(photos)
    return str(photos).strip() not in {"", "[]", "null"}


def _format_dt(value) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M") if hasattr(value, "strftime") else str(value)


def _short_description(value: str | None, limit: int = 260) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text or "Опис не вказано"
    return text[: limit - 1].rstrip() + "…"


def _format_price_offer(value) -> str:
    if value in (None, ""):
        return "договірна"
    text = str(value).rstrip("0").rstrip(".")
    return f"{text} грн" if text else "договірна"


def _format_buyer_offer_notification(context: dict) -> str:
    title = escape(_lead_title(context))
    seller_name = escape(context.get("shop_name") or context.get("seller_name") or "Продавець CarPot")
    lines = [
        "🆕 <b>Нова відповідь на вашу заявку</b>",
        "",
        f"<b>{title}</b>",
        f"🏪 {seller_name}",
        f"💰 {escape(_format_price_offer(context.get('price_offer')))}",
    ]
    seller_city = (context.get("seller_city") or "").strip()
    if seller_city:
        lines.append(f"📍 {escape(seller_city)}")

    message = (context.get("message") or "").strip()
    if message:
        lines.extend(["", "Коментар:", escape(message[:700])])
    return "\n".join(lines)


async def _notify_buyer_about_offer(*, request_id: int, seller_id: int, offer: dict) -> None:
    offer_id = offer.get("id") if offer else None
    if not offer_id:
        return

    event = await ensure_buyer_offer_created_event(
        request_id=request_id,
        seller_id=seller_id,
        offer_id=int(offer_id),
    )
    if event.get("already_exists"):
        logger.info(
            "Buyer offer-created notification already recorded request_id=%s offer_id=%s seller_id=%s event_id=%s",
            request_id,
            offer_id,
            seller_id,
            event.get("id"),
        )
        return

    context_row = await get_buyer_offer_notification_context(
        request_id=request_id,
        seller_id=seller_id,
        offer_id=int(offer_id),
    )
    context = _row_to_dict(context_row)
    buyer_telegram_id = context.get("buyer_telegram_id")
    if not buyer_telegram_id:
        logger.warning(
            "Buyer telegram_id missing for offer notification request_id=%s offer_id=%s seller_id=%s",
            request_id,
            offer_id,
            seller_id,
        )
        await mark_marketplace_notification_event(event.get("id"), status="failed")
        return

    sent = await send_message_to_buyer(
        int(buyer_telegram_id),
        _format_buyer_offer_notification(context),
        parse_mode="HTML",
        reply_markup=buyer_offer_created_notification_kb(request_id),
    )
    if sent:
        await mark_marketplace_notification_event(event.get("id"), status="sent")
        logger.info(
            "Buyer notified about seller offer buyer_telegram_id=%s request_id=%s offer_id=%s",
            buyer_telegram_id,
            request_id,
            offer_id,
        )
    else:
        await mark_marketplace_notification_event(event.get("id"), status="failed")
        logger.warning(
            "Telegram send failure buyer offer notification buyer_telegram_id=%s request_id=%s offer_id=%s",
            buyer_telegram_id,
            request_id,
            offer_id,
        )


def _format_lead_card(lead: dict, *, detailed: bool = False) -> str:
    title = escape(_lead_title(lead))
    city = escape(lead.get("city") or "Місто не вказано")
    category = escape(lead.get("category") or "Категорія не вказана")
    request_type = escape(lead.get("request_type") or "request")
    urgency = URGENCY_LABELS.get(lead.get("urgency"), "⚡ Актуально")
    status = STATUS_LABELS.get(lead.get("marketplace_status"), lead.get("marketplace_status") or "Нова")
    vin = escape(lead.get("vin") or "")
    photos = "📷 Є фото" if _has_photos(lead) else "📷 Без фото"
    offers_count = int(lead.get("offers_count") or 0)
    match_score = lead.get("match_score")
    match_reasons = lead.get("match_reasons")
    if isinstance(match_reasons, str):
        match_reasons_label = match_reasons
    elif match_reasons:
        match_reasons_label = ", ".join(str(reason) for reason in match_reasons)
    else:
        match_reasons_label = None

    lines = [
        "🔥 <b>Нова заявка</b>",
        "",
        f"<b>{title}</b>",
        f"📍 {city}",
        f"📞 {escape(lead.get('buyer_phone') or '—')}",
        f"🧩 {category} · {request_type}",
        f"{urgency}",
    ]

    if vin:
        lines.append(f"VIN: <code>{vin}</code>")

    lines.extend(
        [
            photos,
            f"🕒 {_format_dt(lead.get('created_at'))}",
            f"📌 Статус: {status}",
        ]
    )

    if offers_count:
        lines.append(f"🤝 Пропозицій: {offers_count}")
    if match_score is not None:
        lines.append(f"🎯 Релевантність: {int(match_score)}")
    if detailed and match_reasons_label:
        lines.append(f"🔎 Причини: {escape(match_reasons_label)}")

    if detailed:
        lines.extend(["", escape(_short_description(lead.get("description")))])
    else:
        lines.extend(["", escape(_short_description(lead.get("description"), 120))])

    return "\n".join(lines)


async def _seller_context(telegram_id: int):
    seller = await get_seller_marketplace_profile(telegram_id)
    if not seller:
        return None, []
    seller_dict = dict(seller)
    tags = await get_seller_specialization_tags(seller_dict["id"])
    return seller_dict, tags


async def _hydrate_lead_contacts(lead: dict) -> dict:
    if lead.get("buyer_phone"):
        return lead
    row = await fetchrow(
        """
        SELECT buyer_phone, buyer_telegram
        FROM buyer_requests
        WHERE id = $1 AND entity_type = 'marketplace_request'
        LIMIT 1
        """,
        lead.get("id"),
    )
    if row:
        row_dict = dict(row)
        lead["buyer_phone"] = row_dict.get("buyer_phone")
        lead["buyer_telegram"] = row_dict.get("buyer_telegram")
    return lead


async def _render_inbox(message_or_callback, telegram_id: int):
    seller, tags = await _seller_context(telegram_id)
    if not seller:
        text = "📥 <b>Нові заявки</b>\n\nСпочатку створіть профіль продавця, щоб отримувати релевантні ліди."
        markup = None
    else:
        leads = [dict(row) for row in await list_matching_seller_leads(seller["id"], limit=10)]
        for lead in leads:
            score = score_seller_lead(
                seller_city=seller.get("city"),
                specialization_tags=tags,
                request_city=lead.get("city"),
                category=lead.get("category"),
                request_type=lead.get("request_type"),
                brand=lead.get("brand"),
                model=lead.get("model"),
                urgency=lead.get("urgency"),
                verified=bool(seller.get("is_verified")),
                premium_ready=bool(seller.get("has_site") or seller.get("crm_enabled")),
            )
            lead["match_score"] = min(score.score, 100)

        if leads:
            text = (
                "📥 <b>Нові заявки</b>\n\n"
                "Обирайте релевантний лід і швидко надсилайте пропозицію покупцю."
            )
            markup = seller_leads_inbox_kb(leads)
        else:
            text = (
                "📥 <b>Нові заявки</b>\n\n"
                "Поки немає нових заявок під ваш регіон або спеціалізацію. "
                "Ми покажемо їх тут, щойно зʼявляться релевантні ліди."
            )
            markup = seller_leads_inbox_kb([])

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message_or_callback.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(F.text == "📥 Нові заявки")
async def seller_leads_inbox(message: Message, state: FSMContext):
    await state.clear()
    await _render_inbox(message, message.from_user.id)


@router.callback_query(F.data == "seller_leads:list")
async def seller_leads_inbox_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _render_inbox(callback, callback.from_user.id)


@router.callback_query(F.data.startswith("seller_leads:open:"))
async def seller_lead_open(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    request_id = int(callback.data.rsplit(":", 1)[1])
    seller, _tags = await _seller_context(callback.from_user.id)
    if not seller:
        await callback.message.edit_text("Профіль продавця не знайдено.")
        return

    lead = await get_matching_seller_lead(seller["id"], request_id)
    if not lead:
        await callback.message.edit_text(
            "Заявка вже недоступна або була пропущена.",
            reply_markup=seller_lead_back_kb(),
        )
        return

    await mark_seller_lead_action(seller_id=seller["id"], request_id=request_id, action="viewed")
    logger.info("Seller opened buyer request lead seller_id=%s request_id=%s", seller["id"], request_id)
    lead_card = await _hydrate_lead_contacts(_row_to_dict(lead))
    await callback.message.edit_text(
        _format_lead_card(lead_card, detailed=True),
        parse_mode="HTML",
        reply_markup=seller_lead_actions_kb(request_id),
    )


@router.callback_query(F.data.startswith("seller_leads:skip:"))
async def seller_lead_skip(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    request_id = int(callback.data.rsplit(":", 1)[1])
    seller, _tags = await _seller_context(callback.from_user.id)
    if seller:
        await mark_seller_lead_action(seller_id=seller["id"], request_id=request_id, action="skipped")
        logger.info("Seller skipped buyer request lead seller_id=%s request_id=%s", seller["id"], request_id)
    await callback.message.edit_text(
        "⏭ Заявку пропущено. Ми покажемо інші релевантні ліди.",
        reply_markup=seller_lead_back_kb(),
    )


@router.callback_query(F.data.startswith("seller_leads:decline:"))
async def seller_lead_decline(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    request_id = int(callback.data.rsplit(":", 1)[1])
    seller, _tags = await _seller_context(callback.from_user.id)
    if seller:
        await mark_seller_lead_action(
            seller_id=seller["id"],
            request_id=request_id,
            action="declined",
            metadata={"source": "seller_lead_notification"},
        )
        await cancel_seller_lead_notifications(seller_id=seller["id"], request_id=request_id)
        logger.info("Seller declined buyer request lead seller_id=%s request_id=%s", seller["id"], request_id)

    await callback.message.edit_text(
        "❌ <b>Заявку відхилено.</b>\nВи більше не будете отримувати оновлення по цьому запиту.",
        parse_mode="HTML",
        reply_markup=seller_lead_declined_kb(),
    )


@router.callback_query(F.data.startswith("seller_leads:offer:"))
async def seller_offer_start(callback: CallbackQuery, state: FSMContext):
    request_id = int(callback.data.rsplit(":", 1)[1])
    await callback.answer()
    seller, _tags = await _seller_context(callback.from_user.id)
    if not seller or not await get_matching_seller_lead(seller["id"], request_id):
        await callback.message.edit_text("Заявка вже недоступна.", reply_markup=seller_lead_back_kb())
        return

    await state.set_state(SellerLeadOfferStates.price)
    await state.update_data(request_id=request_id, seller_id=seller["id"])
    await callback.message.edit_text(
        "💰 <b>Вкажіть ціну</b>\n\nНапишіть суму цифрами або “договірна”.",
        parse_mode="HTML",
        reply_markup=seller_offer_skip_step_kb(request_id),
    )


@router.callback_query(F.data.startswith("seller_leads:offer_skip:"))
async def seller_offer_skip_optional(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()
    request_id = int(callback.data.rsplit(":", 1)[1])

    if current_state == SellerLeadOfferStates.price.state:
        await state.update_data(price_offer=None)
        await state.set_state(SellerLeadOfferStates.message)
        await callback.message.edit_text(
            "💬 <b>Коментар до пропозиції</b>\n\nНаприклад: є в наявності, стан хороший, можна відправити сьогодні.",
            parse_mode="HTML",
            reply_markup=seller_lead_back_kb(request_id),
        )
        return

    await callback.message.edit_text("Продовжіть створення пропозиції.", reply_markup=seller_lead_back_kb(data.get("request_id")))


def _price_offer_from_state(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning("Invalid price_offer in seller lead FSM data: %r", value)
        return None


@router.message(SellerLeadOfferStates.price)
async def seller_offer_price(message: Message, state: FSMContext):
    data = await state.get_data()
    text = (message.text or "").replace(" ", "").replace(",", ".")
    if text.lower() in {"договірна", "договiрна", "договорная", "за домовленістю", "задомовленістю"}:
        price = None
    else:
        try:
            price = Decimal(text)
            if price < 0 or price > Decimal("99999999"):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            await message.answer(
                "Вкажіть суму цифрами, наприклад 4500, або напишіть “договірна”.",
                reply_markup=seller_offer_skip_step_kb(data["request_id"]),
            )
            return

    await state.update_data(price_offer=str(price) if price is not None else None)
    await state.set_state(SellerLeadOfferStates.message)
    await message.answer(
        "💬 <b>Коментар до пропозиції</b>\n\nНаприклад: є в наявності, стан хороший, можна відправити сьогодні.",
        parse_mode="HTML",
        reply_markup=seller_lead_back_kb(data["request_id"]),
    )


@router.message(SellerLeadOfferStates.availability)
async def seller_offer_availability(message: Message, state: FSMContext):
    data = await state.get_data()
    availability = (message.text or "").strip()[:180] or None
    await state.update_data(availability_note=availability)
    await state.set_state(SellerLeadOfferStates.message)
    await message.answer(
        "💬 Коментар\n\nКоротко поясніть покупцю, що саме пропонуєте.",
        reply_markup=seller_lead_back_kb(data["request_id"]),
    )


@router.message(SellerLeadOfferStates.message)
async def seller_offer_message(message: Message, state: FSMContext):
    data = await state.get_data()
    request_id = int(data["request_id"])
    seller_id = int(data["seller_id"])
    comment = (message.text or "").strip()

    if len(comment) < 5:
        await message.answer("Додайте короткий коментар — мінімум 5 символів.", reply_markup=seller_lead_back_kb(request_id))
        return

    price_offer = _price_offer_from_state(data.get("price_offer"))
    offer = await create_seller_offer(
        request_id=request_id,
        seller_id=seller_id,
        message=comment[:1200],
        price_offer=price_offer,
        availability_note="Готовий обговорити",
        status="pending",
    )
    await mark_seller_lead_action(seller_id=seller_id, request_id=request_id, action="offered")
    await touch_request_matched(request_id)
    logger.info("Seller offer created seller_id=%s request_id=%s offer_id=%s", seller_id, request_id, offer.get("id") if offer else None)
    try:
        await _notify_buyer_about_offer(request_id=request_id, seller_id=seller_id, offer=dict(offer) if offer else {})
    except Exception as exc:
        logger.warning(
            "Buyer offer notification failed without blocking seller flow request_id=%s offer_id=%s: %s",
            request_id,
            offer.get("id") if offer else None,
            exc,
        )
    await state.clear()

    price = offer.get("price_offer") if offer else price_offer
    availability = offer.get("availability_note") if offer else "Готовий обговорити"
    summary = ["✅ <b>Пропозицію надіслано</b>", "", f"💰 Ціна: {price or 'за домовленістю'}"]
    if availability:
        summary.append(f"🕒 Доступність: {escape(str(availability))}")
    summary.extend(["", "Покупець зможе побачити вашу пропозицію у майбутньому кабінеті заявок."])

    await message.answer("\n".join(summary), parse_mode="HTML", reply_markup=seller_lead_back_kb(request_id))
