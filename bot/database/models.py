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
    CREATE UNIQUE INDEX IF NOT EXISTS uq_models_brand_name
    ON models (brand_id, name);
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS brand_requests (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        brand TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS model_requests (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        brand TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
    );
    """)

    await execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_brand_requests_user_brand
    ON brand_requests (user_id, brand);
    """)

    await execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_model_requests_user_brand_model
    ON model_requests (user_id, brand, model);
    """)


    await execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        role TEXT NOT NULL CHECK (role IN ('super_admin', 'admin', 'manager')),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS admin_sessions (
        id SERIAL PRIMARY KEY,
        admin_user_id INTEGER REFERENCES admin_users(id) ON DELETE CASCADE,
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used_at TIMESTAMP NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS admin_audit_logs (
        id SERIAL PRIMARY KEY,
        actor_admin_id INTEGER NULL REFERENCES admin_users(id),
        action TEXT NOT NULL,
        entity_type TEXT NULL,
        entity_id TEXT NULL,
        payload JSONB DEFAULT '{}'::jsonb,
        ip TEXT NULL,
        user_agent TEXT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await execute("""
    INSERT INTO admin_users (telegram_id, role)
    VALUES (6206952389, 'super_admin')
    ON CONFLICT (telegram_id) DO NOTHING;
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

    await execute("""
    CREATE TABLE IF NOT EXISTS site_leads (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
        site_id INTEGER NULL REFERENCES seller_sites(id) ON DELETE SET NULL,
        subdomain TEXT NOT NULL,
        name TEXT,
        phone TEXT NOT NULL,
        message TEXT,
        status TEXT NOT NULL DEFAULT 'new'
            CHECK (status IN ('new', 'in_progress', 'done', 'rejected')),
        manager_admin_id INTEGER NULL REFERENCES admin_users(id) ON DELETE SET NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await execute("CREATE INDEX IF NOT EXISTS idx_site_leads_seller_id ON site_leads(seller_id);")
    await execute("CREATE INDEX IF NOT EXISTS idx_site_leads_status ON site_leads(status);")
    await execute("CREATE INDEX IF NOT EXISTS idx_site_leads_created_at ON site_leads(created_at);")

    # === NEW FIELDS ===
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS cars_limit INTEGER DEFAULT 1;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS cars_used INTEGER DEFAULT 0;")

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

    await execute("""
    CREATE TABLE IF NOT EXISTS seller_subscriptions (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
        slots INTEGER NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        payment_id INTEGER REFERENCES payments(id) ON DELETE SET NULL
    );
    """)

    await execute(
        "CREATE INDEX IF NOT EXISTS idx_seller_subscriptions_seller_id ON seller_subscriptions(seller_id);"
    )
    await execute(
        "CREATE INDEX IF NOT EXISTS idx_seller_subscriptions_expires_at ON seller_subscriptions(expires_at);"
    )

    await execute(
        "ALTER TABLE services ADD COLUMN IF NOT EXISTS price INTEGER;"
    )
