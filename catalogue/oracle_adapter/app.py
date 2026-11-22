"""CarPot Oracle MySQL catalogue adapter, phase 2: confirmed-table reads only.

This is a separate internal service, NOT a modification to the live Catalogue API.
It cannot read article_links or article_li before the migration finishes.
Every query is an exact indexed SELECT with a hard output cap. Neither OEM
cross-references nor PRD rows establish exact VIN/vehicle part compatibility.
"""
from contextlib import contextmanager
import os
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query

app = FastAPI(title="CarPot Oracle Catalogue Adapter", version="0.2.0", docs_url=None, redoc_url=None)

ROW_LIMIT = 50


def authorize(x_oracle_adapter_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("ORACLE_ADAPTER_KEY", "")
    if not expected or not x_oracle_adapter_key or not secrets.compare_digest(x_oracle_adapter_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def require_database_settings() -> dict:
    names = ("ORACLE_MYSQL_HOST", "ORACLE_MYSQL_PORT", "ORACLE_MYSQL_USER",
             "ORACLE_MYSQL_PASSWORD", "ORACLE_MYSQL_DATABASE")
    if any(not os.environ.get(k) for k in names):
        raise HTTPException(status_code=503, detail="Database access not configured")
    # Adapter must be co-located with Oracle MySQL or use a locally bound SSH/VPN tunnel.
    # Public MySQL access is intentionally not supported.
    if os.environ["ORACLE_MYSQL_HOST"] not in ("127.0.0.1", "localhost"):
        raise HTTPException(status_code=503, detail="Private database connection required")
    if os.environ["ORACLE_MYSQL_USER"].casefold() in ("root", "admin"):
        raise HTTPException(status_code=503, detail="Dedicated read-only database identity required")
    if os.environ["ORACLE_MYSQL_DATABASE"] != "td1q2018":
        raise HTTPException(status_code=503, detail="Unexpected database")
    try:
        port = int(os.environ["ORACLE_MYSQL_PORT"])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=503, detail="Invalid database port") from None
    return {"host": os.environ["ORACLE_MYSQL_HOST"], "port": port,
            "user": os.environ["ORACLE_MYSQL_USER"],
            "password": os.environ["ORACLE_MYSQL_PASSWORD"],
            "database": os.environ["ORACLE_MYSQL_DATABASE"]}


@contextmanager
def database():
    settings = require_database_settings()
    try:
        import pymysql
        connection = pymysql.connect(**settings, charset="utf8mb4", autocommit=False,
                                     connect_timeout=3, read_timeout=5, write_timeout=3,
                                     cursorclass=pymysql.cursors.DictCursor)
    except Exception:
        raise HTTPException(status_code=503, detail="Catalogue source unavailable") from None
    try:
        try:
            with connection.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
                cur.execute("SET SESSION max_execution_time=3000")
                cur.execute("SELECT @@transaction_read_only AS ro")
                if int(cur.fetchone()["ro"]) != 1:
                    raise RuntimeError("Read-only transaction not enforced")
            yield connection
        except HTTPException:
            raise
        except Exception:
            # Never disclose Oracle host, credentials, SQL or driver errors in API responses.
            raise HTTPException(status_code=503, detail="Catalogue query unavailable") from None
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def valid_identifier(value: str) -> str:
    if not value or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise HTTPException(status_code=422, detail="Invalid catalogue identifier")
    return value


def bounded_lookup(conn, sql: str, args: tuple, limit: int) -> dict:
    # The last parameter always means limit + 1 to detect truncation.
    with conn.cursor() as cur:
        cur.execute(sql, (*args, limit + 1))
        rows = cur.fetchall()
    return {"items": rows[:limit], "truncated": len(rows) > limit}


@app.get("/health")
def health():
    # Process health only. No live database query and no misleading fitment claim.
    return {"status": "ok", "service": "oracle-catalogue-adapter", "source_verified_live": False}


@app.get("/api/v1/oracle/oem/by-article", dependencies=[Depends(authorize)])
def oem_by_article(
    supplier_id: int = Query(ge=1, le=65535),
    article_number: str = Query(min_length=1, max_length=64),
    manufacturer_id: int = Query(ge=1),
    limit: int = Query(default=20, ge=1, le=ROW_LIMIT),
):
    """Exact supplier article -> OE references for requested OE manufacturer."""
    article_number = valid_identifier(article_number)
    sql = """SELECT OENbr AS oem_number FROM article_oe FORCE INDEX (supplierid)
             WHERE supplierid=%s AND datasupplierarticlenumber=%s
               AND BINARY datasupplierarticlenumber=BINARY %s
               AND manufacturerId=%s LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql,
                                (supplier_id, article_number, article_number, manufacturer_id), limit)
    return {"supplier_id": supplier_id, "article_number": article_number,
            "manufacturer_id": manufacturer_id, **result, "fitment_verified": False}


@app.get("/api/v1/oracle/oem/by-number", dependencies=[Depends(authorize)])
def articles_by_oem(
    manufacturer_id: int = Query(ge=1),
    oem_number: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=20, ge=1, le=ROW_LIMIT),
):
    """OEM number -> supplier article cross-references; not guaranteed substitution."""
    oem_number = valid_identifier(oem_number)
    sql = """SELECT SupplierId AS supplier_id,
                    PartsDataSupplierArticleNumber AS article_number
             FROM article_cross FORCE INDEX (OENbr)
             WHERE OENbr=%s AND BINARY OENbr=BINARY %s
               AND manufacturerId=%s LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql, (oem_number, oem_number, manufacturer_id), limit)
    return {"manufacturer_id": manufacturer_id, "oem_number": oem_number,
            **result, "cross_reference_only": True, "fitment_verified": False}


@app.get("/api/v1/oracle/vehicles/{car_id}/prd", dependencies=[Depends(authorize)])
def vehicle_prd(car_id: int, limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    """Source car -> PRD/supplier associations; no exact article or VIN fitment."""
    if car_id < 1:
        raise HTTPException(status_code=422, detail="Invalid source modification")
    sql = """SELECT nodeid AS node_id, productid AS product_id,
                    supplierid AS supplier_id
             FROM passanger_car_pds FORCE INDEX (PRIMARY)
             WHERE passangercarid=%s
             ORDER BY nodeid,productid,supplierid LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql, (car_id,), limit)
    return {"source_modification_id": car_id, **result,
            "source_association_only": True, "fitment_verified": False}


# Read-only indexed vehicle identity discovery. These endpoints intentionally do
# not consult article_li/article_links during the running 50+ GiB migration.
# Their IDs are candidate catalogue identities, not verified VIN fitment.
@app.get("/api/v1/oracle/vehicles/manufacturers", dependencies=[Depends(authorize)])
def vehicle_manufacturers(
    name: str = Query(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9 .-]+$"),
    kind: str = Query(pattern=r"^(passenger|commercial)$"),
    limit: int = Query(default=20, ge=1, le=ROW_LIMIT),
):
    # The maker dimension is ~4,380 rows. Keep this one small-table lookup
    # bounded. Never query unindexed article tables or the active import.
    flag = "ispassengercar" if kind == "passenger" else "iscommercialvehicle"
    sql = f"""SELECT id, description AS name FROM manufacturers
              WHERE {flag}='True' AND description LIKE CONCAT(%s,'%%')
                AND description IS NOT NULL AND description!=''
              ORDER BY id LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql, (valid_identifier(name),), limit)
    return {"source": "oracle", "kind": kind, **result,
            "vehicle_identity_only": True, "fitment_verified": False}


@app.get("/api/v1/oracle/vehicles/models", dependencies=[Depends(authorize)])
def vehicle_models(
    manufacturer_id: int = Query(ge=1),
    kind: str = Query(pattern=r"^(passenger|commercial)$"),
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=ROW_LIMIT),
):
    flag = "ispassengercar" if kind == "passenger" else "iscommercialvehicle"
    sql = f"""SELECT id, description AS name, constructioninterval AS construction_interval
              FROM models FORCE INDEX (manufacturerid)
              WHERE manufacturerid=%s AND {flag}='True' AND id>%s
                AND description IS NOT NULL AND description!=''
              ORDER BY id LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql, (manufacturer_id, after), limit)
    return {"source": "oracle", "manufacturer_id": manufacturer_id,
            "kind": kind, "next_after": result["items"][-1]["id"] if result["truncated"] else None,
            **result, "vehicle_identity_only": True, "fitment_verified": False}


@app.get("/api/v1/oracle/vehicles/modifications", dependencies=[Depends(authorize)])
def vehicle_modifications(
    model_id: int = Query(ge=1),
    kind: str = Query(pattern=r"^(passenger|commercial)$"),
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=ROW_LIMIT),
):
    table = "passanger_cars" if kind == "passenger" else "commercial_vehicles"
    sql = f"""SELECT id, modelid AS model_id, description AS name,
                     constructioninterval AS construction_interval
              FROM {table} FORCE INDEX (modelid)
              WHERE modelid=%s AND id>%s
                AND description IS NOT NULL AND description!=''
              ORDER BY id LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql, (model_id, after), limit)
    return {"source": "oracle", "model_id": model_id,
            "kind": kind, "next_after": result["items"][-1]["id"] if result["truncated"] else None,
            **result, "vehicle_identity_only": True, "fitment_verified": False}


@app.get("/api/v1/oracle/vehicles/attributes", dependencies=[Depends(authorize)])
def vehicle_attributes(
    car_id: int = Query(ge=1),
    kind: str = Query(pattern=r"^(passenger|commercial)$"),
    limit: int = Query(default=50, ge=1, le=ROW_LIMIT),
):
    table, column = (("passanger_car_attributes", "passangercarid") if kind == "passenger"
                     else ("commercial_vehicle_attributes", "commercialvehicleid"))
    sql = f"""SELECT attributetype AS attribute_type, displayvalue AS display_value
              FROM {table} FORCE INDEX ({column})
              WHERE {column}=%s AND attributetype IS NOT NULL
                AND displayvalue IS NOT NULL
              LIMIT %s"""
    with database() as conn:
        result = bounded_lookup(conn, sql, (car_id,), limit)
    return {"source": "oracle", "source_modification_id": car_id,
            "kind": kind, **result, "vehicle_identity_only": True,
            "fitment_verified": False}
