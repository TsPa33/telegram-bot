import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


# 🔧 Ініціалізація таблиць
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
    CREATE TABLE IF NOT EXISTS model_requests (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        brand TEXT,
        model TEXT,
        status TEXT DEFAULT 'pending'
    ) 
    """)

    cursor.close()
    conn.close()


# ➕ Додавання користувача (адмін)
def add_user(data: dict):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (name, website, phone) VALUES (%s, %s, %s) RETURNING id",
        (data["name"], data["website"], data["phone"])
    )

    user_id = cursor.fetchone()[0]

    for brand, models in data["models"].items():
        for model in models:
            cursor.execute(
                """
                INSERT INTO models (user_id, brand, model)
                VALUES (%s, %s, %s)
                """,
                (user_id, brand, model)
            )

    cursor.close()
    conn.close()


# 📊 Отримати всі бренди
def get_brands():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT brand
        FROM models
        ORDER BY brand
    """)

    brands = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return brands


# 📊 Отримати моделі по бренду
def get_models_by_brand(brand: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT model
        FROM models
        WHERE brand = %s
        ORDER BY model
    """, (brand,))

    models = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return models


# 🔍 Пошук продавців
def find_by_model(brand: str, model: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.name, u.website, u.phone
        FROM models m
        JOIN users u ON m.user_id = u.id
        WHERE m.brand = %s AND m.model = %s
    """, (brand, model))

    results = cursor.fetchall()

    cursor.close()
    conn.close()

    return results


# ================= MODEL HELPERS =================

def model_exists(brand: str, model: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM models WHERE brand=%s AND model=%s",
        (brand, model)
    )

    exists = cursor.fetchone() is not None

    cursor.close()
    conn.close()

    return exists


def add_model_request(user_id: int, brand: str, model: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO model_requests (user_id, brand, model) VALUES (%s, %s, %s)",
        (user_id, brand, model)
    )

    cursor.close()
    conn.close()
# ================= ADMIN MODEL REQUESTS =================

def get_pending_model_requests():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, user_id, brand, model
        FROM model_requests
        WHERE status = 'pending'
        ORDER BY id
    """)

    requests = cursor.fetchall()

    cursor.close()
    conn.close()

    return requests


def approve_model(request_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    # отримуємо дані заявки
    cursor.execute("""
        SELECT user_id, brand, model
        FROM model_requests
        WHERE id = %s
    """, (request_id,))

    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return False

    user_id, brand, model = row

    # додаємо в models
    cursor.execute("""
        INSERT INTO models (user_id, brand, model)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (user_id, brand, model))

    # оновлюємо статус
    cursor.execute("""
        UPDATE model_requests
        SET status = 'approved'
        WHERE id = %s
    """, (request_id,))

    cursor.close()
    conn.close()

    return True


def reject_model(request_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE model_requests
        SET status = 'rejected'
        WHERE id = %s
    """, (request_id,))

    cursor.close()
    conn.close()
