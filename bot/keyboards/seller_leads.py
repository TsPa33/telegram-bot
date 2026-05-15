from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def seller_leads_inbox_kb(leads) -> InlineKeyboardMarkup:
    buttons = []
    for lead in leads:
        title = " ".join(
            part for part in [lead.get("brand"), lead.get("model"), lead.get("category")] if part
        ).strip() or lead.get("category") or "Заявка"
        city = lead.get("city") or "місто не вказано"
        score = lead.get("match_score")
        score_label = f" · {int(score)}%" if score is not None else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"🔥 {title[:28]} · {city[:14]}{score_label}",
                callback_data=f"seller_leads:open:{lead['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔄 Оновити", callback_data="seller_leads:list")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def seller_lead_actions_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запропонувати", callback_data=f"seller_leads:offer:{request_id}")],
            [InlineKeyboardButton(text="⏭ Пропустити", callback_data=f"seller_leads:skip:{request_id}")],
            [InlineKeyboardButton(text="📥 До заявок", callback_data="seller_leads:list")],
        ]
    )


def seller_lead_back_kb(request_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    if request_id:
        rows.append([InlineKeyboardButton(text="⬅️ До заявки", callback_data=f"seller_leads:open:{request_id}")])
    rows.append([InlineKeyboardButton(text="📥 До заявок", callback_data="seller_leads:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def seller_offer_skip_step_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустити поле", callback_data=f"seller_leads:offer_skip:{request_id}")],
            [InlineKeyboardButton(text="Скасувати", callback_data=f"seller_leads:open:{request_id}")],
        ]
    )
