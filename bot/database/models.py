from bot.database.db import get_connection

def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seller_cars (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            username TEXT,
            brand TEXT,
            model TEXT
        )
    """)

    conn.commit()

    cursor.close()
    conn.close()
