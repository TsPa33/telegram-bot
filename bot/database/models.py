from bot.database.db import cursor, conn


def create_tables():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seller_cars (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT,
        username TEXT,
        brand TEXT,
        model TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seller_cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        username TEXT,
        brand TEXT,
        model TEXT
    )
    """)

    conn.commit()

