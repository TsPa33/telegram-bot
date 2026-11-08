"""Isolated, read-only CarPot Catalogue API. No Warehouse imports."""
import os
import secrets
from contextlib import contextmanager

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from monitor import router as monitor_router

app = FastAPI(title="CarPot Catalogue", version="0.1.0", docs_url=None, redoc_url=None)
app.include_router(monitor_router)

def authorize(x_catalogue_key: str | None = Header(default=None)):
    expected = os.environ.get("CATALOGUE_API_KEY", "")
    if not expected or not x_catalogue_key or not secrets.compare_digest(x_catalogue_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

@contextmanager
def db():
    required = ["MYSQLHOST", "MYSQLPORT", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE"]
    if any(not os.environ.get(name) for name in required):
        raise HTTPException(status_code=503, detail="Catalogue database not configured")
    connection = pymysql.connect(
        host=os.environ["MYSQLHOST"],
        port=int(os.environ["MYSQLPORT"]),
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"],
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        yield connection
    finally:
        connection.close()

@app.get("/health")
def health():
    return {"status": "ok", "service": "carpot-catalogue"}

@app.get("/api/v1/parts", dependencies=[Depends(authorize)])
def search_parts(q: str = Query(min_length=2, max_length=64), limit: int = Query(default=20, ge=1, le=100)):
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT supplier_id, article_number, name_uk, name_source
               FROM catalogue_parts
               WHERE article_number LIKE %s OR name_uk LIKE %s OR name_source LIKE %s
               ORDER BY article_number LIMIT %s""",
            (pattern, pattern, pattern, limit),
        )
        return {"items": cur.fetchall()}

@app.get("/api/v1/oem", dependencies=[Depends(authorize)])
def search_oem(number: str = Query(min_length=2, max_length=64), limit: int = Query(default=50, ge=1, le=100)):
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT o.oem_number, o.oem_manufacturer_id, o.supplier_id,
                      o.article_number, p.name_uk, p.name_source
               FROM catalogue_oem o
               LEFT JOIN catalogue_parts p
                 ON p.supplier_id=o.supplier_id AND p.article_number=o.article_number
               WHERE o.oem_number=%s LIMIT %s""",
            (number, limit),
        )
        return {"items": cur.fetchall()}


@app.get("/api/v1/volvo/article", dependencies=[Depends(authorize)])
def volvo_article_lookup(
    supplier_id: int = Query(ge=1, le=65535),
    article_number: str = Query(min_length=1, max_length=32),
):
    """Read-only OEM enrichment by exact verified supplier ID + article key.

    Does not assert fitment, does not fetch images, and never creates stock.
    The supplier-to-brand mapping must be validated before Warehouse calls it.
    """
    article_number = article_number.strip()
    if not article_number or any(ch in article_number for ch in ("\x00", "\n", "\r")):
        raise HTTPException(422, detail="Invalid article number")
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT supplier_id, article_number, name_uk, name_source
               FROM catalogue_parts
               WHERE supplier_id=%s AND article_number=%s
               LIMIT 1""",
            (supplier_id, article_number),
        )
        part = cur.fetchone()
        cur.execute(
            """SELECT oem_number
               FROM catalogue_oem
               WHERE supplier_id=%s AND article_number=%s
                 AND oem_manufacturer_id=120
               ORDER BY oem_number LIMIT 101""",
            (supplier_id, article_number),
        )
        rows = cur.fetchall()
    return {
        "source": "carpot-catalogue",
        "vehicle_manufacturer": "Volvo",
        "vehicle_manufacturer_id": 120,
        "supplier_id": supplier_id,
        "article_number": article_number,
        "part": part,
        "oem_numbers": [row["oem_number"] for row in rows[:100]],
        "oem_numbers_truncated": len(rows) > 100,
        "fitment_verified": False,
        "vehicle_modification": None,
        "photo": None,
        "note": "OEM cross references do not prove compatibility with a given K-Type/VIN.",
    }
