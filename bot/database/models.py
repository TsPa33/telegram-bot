import logging
import os

from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from bot.database.base import execute, fetchrow

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _password_matches(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        return pwd_context.verify(password, password_hash)
    except (UnknownHashError, ValueError):
        return False


async def bootstrap_crm_admin_password():
    telegram_id_raw = os.getenv("CRM_ADMIN_TELEGRAM_ID")
    username = os.getenv("CRM_ADMIN_USERNAME")
    password = os.getenv("CRM_ADMIN_PASSWORD")

    if not telegram_id_raw or not username or not password:
        return

    username = username.strip()
    if not username:
        return

    try:
        telegram_id = int(telegram_id_raw)
    except ValueError:
        return

    admin = await fetchrow(
        """
        SELECT id, username, password_hash
        FROM admin_users
        WHERE telegram_id = $1
        LIMIT 1
        """,
        telegram_id,
    )

    if not admin:
        return

    password_matches = _password_matches(password, admin["password_hash"])
    next_password_hash = (
        admin["password_hash"] if password_matches else pwd_context.hash(password)
    )

    if admin["username"] == username and password_matches:
        return

    await execute(
        """
        UPDATE admin_users
        SET username = $2, password_hash = $3
        WHERE id = $1
        """,
        admin["id"],
        username,
        next_password_hash,
    )
    logger.info("CRM admin password initialized")


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
        password_hash TEXT,
        role TEXT NOT NULL CHECK (role IN ('super_admin', 'admin', 'manager')),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await execute("ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS password_hash TEXT;")


    await execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        username TEXT,
        full_name TEXT,
        status TEXT NOT NULL DEFAULT 'open'
            CHECK (status IN ('open', 'in_progress', 'closed')),
        assigned_admin_id BIGINT,
        subject TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        closed_at TIMESTAMP
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS support_messages (
        id SERIAL PRIMARY KEY,
        ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
        sender_type TEXT NOT NULL
            CHECK (sender_type IN ('user', 'admin', 'system')),
        sender_telegram_id BIGINT,
        message_text TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS support_assignments (
        id SERIAL PRIMARY KEY,
        ticket_id INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
        admin_telegram_id BIGINT NOT NULL,
        assigned_by BIGINT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """)

    await execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_telegram_status ON support_tickets(telegram_id, status);")
    await execute("CREATE INDEX IF NOT EXISTS idx_support_tickets_status_updated ON support_tickets(status, updated_at DESC);")
    await execute("CREATE INDEX IF NOT EXISTS idx_support_messages_ticket_created ON support_messages(ticket_id, created_at);")
    await execute("CREATE INDEX IF NOT EXISTS idx_support_assignments_ticket_created ON support_assignments(ticket_id, created_at);")

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

    await bootstrap_crm_admin_password()

    await execute("""
    CREATE TABLE IF NOT EXISTS sellers (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        phone TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # === SELLER FIELDS ===
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS cars_limit INTEGER DEFAULT 1;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS cars_used INTEGER DEFAULT 0;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS shop_name TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS name TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS website TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS city TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS description TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS photo_id TEXT;")
    await execute("ALTER TABLE sellers ADD COLUMN IF NOT EXISTS has_site BOOLEAN DEFAULT FALSE;")

    await execute("""
    CREATE TABLE IF NOT EXISTS promo_activations (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        promo_code TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        activated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMP NOT NULL,
        ads_budget_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
        manager_assigned BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        UNIQUE (telegram_id, promo_code)
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
        order_id TEXT UNIQUE NOT NULL,
        amount NUMERIC(10,2) NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        product TEXT NOT NULL DEFAULT 'garage',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS services (
        id SERIAL PRIMARY KEY,
        seller_id BIGINT NOT NULL,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        city TEXT NOT NULL,
        address TEXT NOT NULL,
        description TEXT,
        website TEXT,
        photo_id TEXT,
        price INTEGER,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS service_stats (
        service_id INT PRIMARY KEY,
        views INT DEFAULT 0,
        calls INT DEFAULT 0,
        clicks INT DEFAULT 0
    );
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS seller_sites (
        id BIGSERIAL PRIMARY KEY,
        seller_id BIGINT NOT NULL UNIQUE REFERENCES sellers(id) ON DELETE CASCADE,
        subdomain TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'draft',
        config_draft JSONB NOT NULL DEFAULT '{}'::jsonb,
        config_live JSONB NOT NULL DEFAULT '{}'::jsonb,
        has_custom_domain BOOLEAN NOT NULL DEFAULT FALSE,
        custom_domain TEXT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)

    await execute("""
    UPDATE seller_sites ss
    SET subdomain = lower(trim(ss.subdomain))
    WHERE ss.subdomain <> lower(trim(ss.subdomain))
      AND NOT EXISTS (
          SELECT 1
          FROM seller_sites other
          WHERE other.id <> ss.id
            AND lower(trim(other.subdomain)) = lower(trim(ss.subdomain))
      );
    """)

    await execute("""
    CREATE INDEX IF NOT EXISTS idx_seller_sites_subdomain
    ON seller_sites (subdomain);
    """)

    await execute("""
    CREATE INDEX IF NOT EXISTS idx_seller_sites_seller_id
    ON seller_sites (seller_id);
    """)

    await execute("""
    CREATE TABLE IF NOT EXISTS site_leads (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER NOT NULL REFERENCES sellers(id) ON DELETE CASCADE,
        site_id BIGINT NULL REFERENCES seller_sites(id) ON DELETE SET NULL,
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

    await execute("""
    CREATE INDEX IF NOT EXISTS idx_seller_subscriptions_seller_id
    ON seller_subscriptions(seller_id);
    """)

    await execute("""
    CREATE INDEX IF NOT EXISTS idx_seller_subscriptions_expires_at
    ON seller_subscriptions(expires_at);
    """)

    await execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS product TEXT DEFAULT 'garage';")
    await execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS price INTEGER;")
