from bot.database.base import execute


async def create_tables():
    await execute("""
    CREATE TABLE IF NOT EXISTS brands (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS models (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS sellers (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)


    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS shop_name TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS name TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS website TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS city TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS description TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS photo_id TEXT;")

    await execute("""
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

    await execute("""
    CREATE TABLE IF NOT EXISTS car_views (
        car_id INTEGER NOT NULL REFERENCES seller_cars(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_car_views_car_user UNIQUE (car_id, user_id)
    );
    """)

    await execute("CREATE INDEX IF NOT EXISTS idx_model_id ON seller_cars(model_id);")
    await execute("CREATE INDEX IF NOT EXISTS idx_status ON seller_cars(status);")
    await execute("CREATE INDEX IF NOT EXISTS idx_seller_id ON seller_cars(seller_id);")
    await execute("CREATE INDEX IF NOT EXISTS idx_brand_id ON models(brand_id);")
