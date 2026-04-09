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
    CREATE TABLE IF NOT EXISTS brands (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        brand TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS models (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        model TEXT
    )
    """)

    cursor.close()
    conn.close()


# ➕ Додавання користувача
def add_user(data: dict):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (name, website, phone) VALUES (%s, %s, %s) RETURNING id",
        (data["name"], data["website"], data["phone"])
    )

    user_id = cursor.fetchone()[0]

def add_user(data: dict):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (name, website, phone) VALUES (%s, %s, %s) RETURNING id",
        (data["name"], data["website"], data["phone"])
    )

    user_id = cursor.fetchone()[0]

    # 🔥 нова логіка
    for brand, models in data["models"].items():
        for model in models:
            cursor.execute(
    "INSERT INTO models (user_id, brand, model) VALUES (%s, %s, %s)",
    (user_id, brand, model)
)

    cursor.close()
    conn.close()
