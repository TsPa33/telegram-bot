import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# ================= INIT =================

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        website TEXT,
        phone TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS models (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        brand TEXT,
        model TEXT,
        UNIQUE (brand, model)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sellers (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE,
        username TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS seller_cars (
        id SERIAL PRIMARY KEY,
        seller_id INTEGER,
        model_id INTEGER,
        photo_id TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.close()
    conn.close()


# ================= GET DATA =================

def get_brands():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT brand FROM models ORDER BY brand")
    data = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()
    return data


def get_models_by_brand(brand: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT model FROM models
        WHERE LOWER(brand) = LOWER(%s)
        ORDER BY model
    """, (brand,))

    data = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()
    return data


def find_cars(brand: str, model: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            s.username,
            m.brand,
            m.model,
            sc.photo_id
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE LOWER(m.brand) = LOWER(%s)
        AND LOWER(m.model) = LOWER(%s)
        AND sc.status = 'active'
        LIMIT 10
    """, (brand, model))

    data = cursor.fetchall()

    cursor.close()
    conn.close()
    return data


# ================= HELPERS =================

def get_model_id(brand: str, model: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM models
        WHERE LOWER(brand)=LOWER(%s)
        AND LOWER(model)=LOWER(%s)
    """, (brand, model))

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    return row[0] if row else None


def model_exists(brand: str, model: str):
    return get_model_id(brand, model) is not None


# ================= SELLERS =================

def get_or_create_seller(telegram_id: int, username: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM sellers WHERE telegram_id=%s", (telegram_id,))
    row = cursor.fetchone()

    if row:
        seller_id = row[0]
    else:
        cursor.execute("""
            INSERT INTO sellers (telegram_id, username)
            VALUES (%s, %s)
            RETURNING id
        """, (telegram_id, username))
        seller_id = cursor.fetchone()[0]

    cursor.close()
    conn.close()
    return seller_id


def add_seller_car(seller_id: int, model_id: int, photo_id: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO seller_cars (seller_id, model_id, photo_id)
        VALUES (%s, %s, %s)
    """, (seller_id, model_id, photo_id))

    cursor.close()
    conn.close()


def get_seller_cars(telegram_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT m.brand, m.model
        FROM seller_cars sc
        JOIN sellers s ON sc.seller_id = s.id
        JOIN models m ON sc.model_id = m.id
        WHERE s.telegram_id = %s
    """, (telegram_id,))

    data = cursor.fetchall()

    cursor.close()
    conn.close()
    return data
