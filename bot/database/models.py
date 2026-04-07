from bot.database.db import get_connection


# 🔹 Таблиця авто продавців (поточна)
def create_seller_cars_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seller_cars (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT,
        username TEXT,
        brand TEXT,
        model TEXT
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()


# 🔹 Таблиця продавців (нова)
def create_sellers_table():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sellers (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        name TEXT,
        company_name TEXT,
        phone TEXT,
        telegram_link TEXT,
        city TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    cursor.close()
    conn.close()


# 🔥 Головна функція (викликається при старті бота)
def create_tables():
    create_seller_cars_table()
    create_sellers_table()
