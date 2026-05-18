from html import escape

from bot.config import SELLER_CRM_BASE_URL


def _clean_text(value: str | None, limit: int = 120) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    if not normalized:
        return None
    return normalized[:limit]


def _lead_detail_text(value: str | None, title: str, limit: int = 180) -> str | None:
    lines = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("Запит:", "Потрібно:")):
            line = line.split(":", 1)[1].strip()
        if line and line.lower() != title.lower():
            lines.append(line)
    return _clean_text(" ".join(lines), limit)


def marketplace_lead_title(row: dict | None) -> str:
    if not row:
        return "Заявка CarPot"
    description = _clean_text(row.get("description"), 200)
    if description:
        for raw_line in str(row.get("description") or "").splitlines():
            line = raw_line.strip()
            if line.startswith("Запит:") or line.startswith("Потрібно:"):
                title = _clean_text(line.split(":", 1)[1], 120)
                if title:
                    return title
    title = _clean_text(" ".join(part for part in [row.get("brand"), row.get("model"), row.get("category")] if part), 120)
    return title or description or "Заявка CarPot"


def crm_base_url() -> str:
    return (SELLER_CRM_BASE_URL or "https://crm.carpot.com.ua").rstrip("/")


async def seller_crm_context_url(seller_id: int | None, path: str = "") -> str | None:
    if not seller_id:
        return None
    from bot.database.repositories.seller_crm_repo import get_crm_account_by_seller

    account = await get_crm_account_by_seller(int(seller_id))
    if not account:
        return None
    slug = (account.get("crm_slug") or "").strip()
    if not slug:
        return None
    normalized_path = path if path.startswith("/") else f"/{path}" if path else ""
    return f"{crm_base_url()}/crm/seller/{slug}{normalized_path}"


def format_new_lead_notification(request_row: dict, *, waiting_response: int | None = None) -> str:
    title = marketplace_lead_title(request_row)
    vehicle = _clean_text(" ".join(part for part in [request_row.get("brand"), request_row.get("model")] if part), 100)
    city = _clean_text(request_row.get("city"), 80)
    details = _lead_detail_text(request_row.get("description"), title, 180)

    lines = ["<b>Нова заявка</b>", "", "Клієнт шукає:", f"<b>{escape(title)}</b>"]
    if vehicle and vehicle.lower() not in title.lower():
        lines.extend(["", escape(vehicle)])
    if city:
        lines.append(escape(city))
    if details and details != title:
        lines.extend(["", escape(details)])

    if waiting_response and waiting_response > 1:
        lines.extend(["", f"Очікують відповіді: {int(waiting_response)}"])

    return "\n".join(lines)


def format_site_lead_notification(*, name: str | None, phone: str | None, message: str | None, subdomain: str | None) -> str:
    lines = ["<b>Нова заявка з сайту</b>", ""]
    if message:
        lines.extend(["Клієнт пише:", escape(_clean_text(message, 180) or "—"), ""])
    if name:
        lines.append(f"Імʼя: {escape(_clean_text(name, 80) or '—')}")
    if phone:
        lines.append(f"Телефон: {escape(_clean_text(phone, 40) or '—')}")
    if subdomain:
        lines.append(f"Сайт: {escape(_clean_text(subdomain, 80) or '—')}")
    return "\n".join(lines)


def format_accepted_offer_notification(offer: dict) -> str:
    title = marketplace_lead_title(
        {
            "description": offer.get("request_description"),
            "brand": offer.get("brand"),
            "model": offer.get("model"),
            "category": offer.get("category") or offer.get("request_type"),
        }
    )
    lines = ["<b>Покупець обрав вашу пропозицію</b>", "", escape(title)]
    buyer_city = _clean_text(offer.get("buyer_city"), 80)
    if buyer_city:
        lines.append(escape(buyer_city))
    buyer_phone = _clean_text(offer.get("buyer_phone"), 40)
    if buyer_phone:
        lines.extend(["", f"Телефон клієнта: {escape(buyer_phone)}"])
    lines.extend(["", "Відкрийте заявку та звʼяжіться з клієнтом."])
    return "\n".join(lines)
