from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


BUYER_REQUESTS_NAMESPACE = "buyer_requests"


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
        username = (offer.get("seller_username") or "").strip().lstrip("@")
        if username:
            rows.append([InlineKeyboardButton(text="Написати", url=f"https://t.me/{username}")])
        else:
            rows.append([
                InlineKeyboardButton(
                    text="Написати",
                    callback_data=f"{BUYER_REQUESTS_NAMESPACE}:contact:{request_id}:{offer_id}",
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text="Обрати",
                callback_data=f"{BUYER_REQUESTS_NAMESPACE}:select:{request_id}:{offer_id}",
            )
        ])

    if not offers:
        rows.append([
            InlineKeyboardButton(
                text="🔄 Оновити",
                callback_data=f"{BUYER_REQUESTS_NAMESPACE}:open:{request_id}:{page}",
            )
        ])

    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"{BUYER_REQUESTS_NAMESPACE}:page:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


