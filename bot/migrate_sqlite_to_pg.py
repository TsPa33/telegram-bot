import asyncio
import sqlite3
import asyncpg
import os


SQLITE_PATH = "bot/database.db"


async def migrate():
    # 🔹 SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # 🔹 Postgres
    pg = await asyncpg.connect(
    "postgresql://postgres:MykVFDrTAfWGcvqxJMnBNOgkqlETYNIA@maglev.proxy.rlwy.net:28161/railway"
)

    print("🚀 Migration started")

    # ================= SELLERS =================

    sellers = sqlite_cursor.execute("SELECT * FROM sellers").fetchall()

    for s in sellers:
        await pg.execute("""
            INSERT INTO sellers (
                id, telegram_id, name, shop_name,
                phone, website, city, is_verified
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (id) DO NOTHING
        """,
            s["id"],
            s["telegram_id"],
            s["name"],
            s["shop_name"],
            s["phone"],
            s["website"],
            s["city"],
            s["is_verified"]
        )

    print(f"✅ Sellers migrated: {len(sellers)}")

    # ================= CARS =================

    cars = sqlite_cursor.execute("SELECT * FROM seller_cars").fetchall()

    for c in cars:
        await pg.execute("""
            INSERT INTO seller_cars (
                id, seller_id, model_id,
                photo_id, description,
                views, phone_clicks, site_clicks,
                status
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (id) DO NOTHING
        """,
            c["id"],
            c["seller_id"],
            c["model_id"],
            c["photo_id"],
            c["description"],
            c["views"],
            c["phone_clicks"],
            c["site_clicks"],
            c["status"]
        )

    print(f"✅ Cars migrated: {len(cars)}")

    await pg.close()
    sqlite_conn.close()

    print("🎉 DONE")


if __name__ == "__main__":
    asyncio.run(migrate())
