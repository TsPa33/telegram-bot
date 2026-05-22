from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

CATEGORY_SLUG_TO_NAME = {
    "body": "Body",
    "optics": "Optics",
    "engine": "Engine",
    "transmission": "Transmission",
    "suspension": "Suspension",
    "brakes": "Brakes",
    "interior": "Interior",
    "electric": "Electrical",
    "cooling": "Cooling / AC",
    "glass": "Mirrors / Glass",
}
CATEGORY_NAME_TO_SLUG = {v: k for k, v in CATEGORY_SLUG_TO_NAME.items()}


def post_car_created_parts_kb(car_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Manage Parts", callback_data=f"part:car:{car_id}")],
        [InlineKeyboardButton(text="📋 My Vehicles", callback_data="nav:garage")],
        [InlineKeyboardButton(text="🏠 Seller Menu", callback_data="nav:seller")],
    ])


def part_categories_kb(car_id: int, categories: list[dict]):
    rows = []
    for category in categories:
        slug = CATEGORY_NAME_TO_SLUG.get(category["category"])
        if not slug:
            continue
        rows.append([InlineKeyboardButton(
            text=f"{category['category']} — {category['total']} / active {category['active']}",
            callback_data=f"part:cat:{car_id}:{slug}",
        )])
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data=f"part:back_car:{car_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def part_list_kb(car_id: int, category_slug: str, parts: list[dict]):
    rows = [[InlineKeyboardButton(text=f"🔧 {p['name']} ({p['status']})", callback_data=f"part:view:{p['id']}")] for p in parts]
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data=f"part:car:{car_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def part_card_kb(part_id: int, car_id: int, category_slug: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Available", callback_data=f"part:available:{part_id}"), InlineKeyboardButton(text="📝 Draft", callback_data=f"part:draft:{part_id}")],
        [InlineKeyboardButton(text="💰 Price", callback_data=f"part:price:{part_id}"), InlineKeyboardButton(text="🖼 Photo", callback_data=f"part:photo:{part_id}")],
        [InlineKeyboardButton(text="🧾 Description", callback_data=f"part:desc:{part_id}"), InlineKeyboardButton(text="🏁 Sold", callback_data=f"part:sold:{part_id}")],
        [InlineKeyboardButton(text="🙈 Hidden", callback_data=f"part:hidden:{part_id}")],
        [InlineKeyboardButton(text="⬅ Category", callback_data=f"part:back_cat:{car_id}:{category_slug}")],
    ])
