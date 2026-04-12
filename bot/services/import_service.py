from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.model_repo import get_model_id
from bot.database.base import execute


# ================= PARSER =================

async def parse_seller_file(text: str):
    rows = []

    for line in text.split("\n"):
        line = line.strip()

        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]

        # очікуємо рівно 6 колонок
        if len(parts) != 6:
            continue

        shop_name, website, phone, name, brand, model = parts

        rows.append({
            "shop_name": shop_name,
            "website": website,
            "phone": phone,
            "name": name,
            "brand": brand,
            "model": model
        })

    return rows


# ================= SAVE =================

async def save_parsed_data(rows: list[dict]):
    for row in rows:
        try:
            # ================= SELLER =================
            # унікальність через phone
            telegram_id = hash(row["phone"])

            seller = await get_or_create_seller(
                telegram_id=telegram_id,
                username=None
            )

            # оновлюємо профіль
            await execute("""
                UPDATE sellers
                SET
                    shop_name = $1,
                    website = $2,
                    phone = $3,
                    name = $4
                WHERE id = $5
            """,
            row["shop_name"],
            row["website"],
            row["phone"],
            row["name"],
            seller["id"]
            )

            # ================= MODEL =================
            model_id = await get_model_id(
                row["brand"],
                row["model"]
            )

            if not model_id:
                continue

            # ================= INSERT =================
            await execute("""
                INSERT INTO seller_cars (
                    seller_id,
                    model_id,
                    photo_id,
                    description,
                    status,
                    is_catalog
                )
                VALUES ($1, $2, NULL, '', 'active', TRUE)
                ON CONFLICT DO NOTHING
            """,
            seller["id"],
            model_id
            )

        except Exception as e:
            # щоб імпорт не падав повністю
            print(f"IMPORT ERROR: {e}")
            continue
