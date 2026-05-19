active_buyer_chat_by_user: dict[int, int] = {}


def set_active_buyer_chat(*, buyer_telegram_id: int, lead_id: int) -> None:
    active_buyer_chat_by_user[int(buyer_telegram_id)] = int(lead_id)


def is_buyer_in_chat(*, buyer_telegram_id: int, lead_id: int) -> bool:
    return active_buyer_chat_by_user.get(int(buyer_telegram_id)) == int(lead_id)
