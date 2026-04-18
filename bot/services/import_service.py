from bot.database.repositories.seller_repo import get_or_create_seller
from bot.database.repositories.model_repo import get_model_id
from bot.database.base import execute
import hashlib
import re


# ================= PARSER =================

async def parse_seller_file(text: str):
    rows = []

    for line_no, line in enumerate(text.splitlines(), start=1):
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
            "model": model,
            "_line_no": line_no
        })

    return rows


# ================= SAVE =================

def _normalize_phone(phone: str) -> str:
    value = (phone or "").strip()
    digits = re.sub(r"[^\d+]", "", value)
    return digits or value


def _stable_telegram_id_from_phone(phone: str) -> int:
    normalized = _normalize_phone(phone)
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)

async def save_parsed_data(rows: list[dict]):
    inserted_rows = 0
    unique_pairs: set[tuple[int, int]] = set()

    for row in rows:
        try:
            print("ROW:", row)

            # ================= SELLER =================
            # унікальність через phone
            telegram_id = _stable_telegram_id_from_phone(row["phone"])

            seller = await get_or_create_seller(
                telegram_id=telegram_id,
                username=None
            )
            print("SELLER:", row["phone"], seller["id"])

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
            print("MODEL:", row["brand"], row["model"], model_id)

            if not model_id:
                continue

            # ================= INSERT =================
            print("INSERT:", seller["id"], model_id)
            unique_pairs.add((seller["id"], model_id))

            await execute("""
                INSERT INTO seller_cars (
                    seller_id,
                    model_id,
                    photo_id,
                    description
                )
                VALUES ($1, $2, NULL, '')
            """,
            seller["id"],
            model_id
            )
            inserted_rows += 1

        except Exception as e:
            # щоб імпорт не падав повністю
            print(f"IMPORT ERROR: {e}")
            continue

    print(f"Imported {inserted_rows} seller_cars rows")
    print(f"Unique (seller_id, model_id) pairs: {len(unique_pairs)}")
    return inserted_rows
