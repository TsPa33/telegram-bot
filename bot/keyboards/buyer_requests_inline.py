from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


BUYER_REQUESTS_NAMESPACE = "buyer_requests"
BUYER_OFFER_NAMESPACE = "buyer_offer"


def request_list_kb(requests, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for index, request in enumerate(requests, start=1):
        rows.append([
            InlineKeyboardButton(
                text=f"Відкрити {index}",
                callback_data=f"{BUYER_REQUESTS_NAMESPACE}:open:{request['id']}:{page}",
            )
        ])

    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="‹", callback_data=f"{BUYER_REQUESTS_NAMESPACE}:page:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=f"{BUYER_REQUESTS_NAMESPACE}:noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="›", callback_data=f"{BUYER_REQUESTS_NAMESPACE}:page:{page + 1}"))
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🔎 Новий пошук", callback_data="buyer:find")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def request_details_kb(request_id: int, offers, *, page: int = 1) -> InlineKeyboardMarkup:
    rows = []
    for offer in offers[:5]:
        offer_id = offer["id"]
        is_selected = offer.get("is_selected_match") or offer.get("status") == "accepted"
        rows.append([
            InlineKeyboardButton(
                text="Написати",
                callback_data=f"{BUYER_OFFER_NAMESPACE}:contact:{offer_id}",
            ),
            InlineKeyboardButton(
                text="✅ Обрано" if is_selected else "Обрати",
                callback_data=f"{BUYER_REQUESTS_NAMESPACE}:noop"
                if is_selected
                else f"{BUYER_OFFER_NAMESPACE}:select:{offer_id}",
            ),
        ])

    if not offers:
        rows.append([
            InlineKeyboardButton(
                text="🔄 Оновити",
                callback_data=f"{BUYER_REQUESTS_NAMESPACE}:open:{request_id}:{page}",
            )
        ])

    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"{BUYER_OFFER_NAMESPACE}:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def buyer_offer_created_notification_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Переглянути заявку",
                    callback_data=f"{BUYER_REQUESTS_NAMESPACE}:open:{request_id}:1",
                )
            ],
            [InlineKeyboardButton(text="🔎 Новий пошук", callback_data="buyer:find")],
        ]
    )


def buyer_selected_offer_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мої заявки", callback_data="buyer:requests")],
            [InlineKeyboardButton(text="🔎 Новий пошук", callback_data="buyer:find")],
        ]
    )
