import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


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

    conn.commit()
    cursor.close()
    conn.close()
