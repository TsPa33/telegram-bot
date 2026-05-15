def build_seller_trust_indicators(seller_offer: dict) -> list[str]:
    indicators: list[str] = []

    if seller_offer.get("is_verified"):
        indicators.append("✅ Верифікований продавець")
    if seller_offer.get("crm_enabled") or seller_offer.get("has_site"):
        indicators.append("🏪 Активний бізнес у CarPot")
    if seller_offer.get("seller_website"):
        indicators.append("🌐 Є сайт")

    successful = int(seller_offer.get("successful_offers") or 0)
    if successful > 0:
        indicators.append(f"🤝 Успішні угоди: {successful}")

    activity = int(seller_offer.get("marketplace_activity") or 0)
    if activity > 0:
        indicators.append("⚡ Відповідає на заявки")

    return indicators
