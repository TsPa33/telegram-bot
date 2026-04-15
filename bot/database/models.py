from bot.database.db import get_connection


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # 🔹 brands
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS brands (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """)

    # 🔹 models
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS models (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE
    );
    """)

    # 🔹 sellers
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sellers (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 🔹 seller_cars
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seller_cars (
        id SERIAL PRIMARY KEY,

        seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
        model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,

        photo_id TEXT,
        description TEXT,

        status INTEGER DEFAULT 1,

        views INTEGER DEFAULT 0,
        phone_clicks INTEGER DEFAULT 0,
        site_clicks INTEGER DEFAULT 0,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 🔥 ІНДЕКСИ (ДУЖЕ ВАЖЛИВО)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_model_id ON seller_cars(model_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON seller_cars(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seller_id ON seller_cars(seller_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_brand_id ON models(brand_id);")

    conn.commit()
    cursor.close()
    conn.close()
