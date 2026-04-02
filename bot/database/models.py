from bot.database.db import cursor, conn


def create_tables():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        role TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seller_cars (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        brand TEXT,
        model TEXT
    )
    """)

    conn.commit()
