"""Internal, read-only Oracle MySQL catalogue adapter."""
from contextlib import contextmanager
import os
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query

app = FastAPI(title="CarPot Oracle Catalogue Adapter", version="0.2.0", docs_url=None, redoc_url=None)

ROW_LIMIT = 50
CATEGORY_LIMIT = 256
CatalogueKind = Literal["passenger", "commercial"]


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
    sql = f"""SELECT DISTINCT id, description AS name FROM manufacturers
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
    sql = f"""SELECT DISTINCT id, description AS name, constructioninterval AS construction_interval
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


def audit_identity(conn, car_id, kind):
    table, flag = (("passanger_cars", "ispassengercar") if kind == "passenger"
                   else ("commercial_vehicles", "iscommercialvehicle"))
    with conn.cursor() as cur:
        cur.execute(f"""SELECT DISTINCT m.manufacturerid AS manufacturer_id
                        FROM {table} AS c FORCE INDEX (PRIMARY)
                        LEFT JOIN models AS m ON m.id=c.modelid AND m.{flag}='True'
                        WHERE c.id=%s LIMIT 2""", (car_id,))
        makers = cur.fetchall()
    if not makers:
        raise HTTPException(404, "Modification absent from requested catalogue")
    if len(makers) != 1 or not makers[0]["manufacturer_id"]:
        raise HTTPException(503, "Ambiguous catalogue manufacturer")
    return makers[0]["manufacturer_id"]


def audit_source(kind):
    if kind == "passenger":
        return "passanger_car_pds", "passangercarid", 2
    # The Oracle schema's commercial linkage type must be confirmed on the
    # source before it can be enabled. Passenger linkage type is reserved.
    value = os.getenv("ORACLE_COMMERCIAL_LINKAGE_TYPE", "")
    if not value.isascii() or not value.isdecimal() or len(value) > 5:
        raise HTTPException(503, "Commercial linkage type not configured")
    linkage_type = int(value)
    if not 1 <= linkage_type <= 65535 or linkage_type == 2:
        raise HTTPException(503, "Invalid commercial linkage type")
    return "commercial_vehicle_pds", "commercialvehicleid", linkage_type


AUDIT_CTES = """
WITH links AS (
    SELECT DISTINCT productid, supplierid,
           CAST(datasupplierarticlenumber AS BINARY) AS article_key,
           datasupplierarticlenumber AS article_number
    FROM article_links FORCE INDEX (linkageid)
    WHERE linkageid=%s AND linkagetypeid=%s AND supplierid > 0
      AND datasupplierarticlenumber <> ''
), articles AS (
    SELECT DISTINCT supplierid, article_key, article_number FROM links
), oems AS (
    SELECT DISTINCT a.supplierid, a.article_key, CAST(o.OENbr AS BINARY) AS oem_key
    FROM articles AS a
    STRAIGHT_JOIN article_oe AS o FORCE INDEX (supplierid)
       ON o.supplierid=a.supplierid
      AND o.datasupplierarticlenumber=a.article_number
      AND CAST(o.datasupplierarticlenumber AS BINARY)=a.article_key
      AND o.manufacturerId=%s
    WHERE o.OENbr <> ''
)
"""


def audit_response(car_id, kind, manufacturer_id):
    return dict(source="oracle", source_modification_id=car_id, kind=kind,
                manufacturer_id=manufacturer_id, source_association_only=True,
                fitment_verified=False)


@app.get("/api/v1/oracle/vehicles/{car_id}/audit", dependencies=[Depends(authorize)])
def vehicle_audit(kind: CatalogueKind, car_id: int = Path(ge=1)):
    table, column, linkage_type = audit_source(kind)
    sql = AUDIT_CTES + f""", prd_links AS (
        SELECT nodeid, productid, supplierid
        FROM {table} FORCE INDEX (PRIMARY)
        WHERE {column}=%s
    ), scoped_prd AS (
        SELECT 0 AS scope_id, NULL AS category_id, productid FROM prd_links
        UNION ALL
        SELECT 1, nodeid, productid FROM prd_links
    ), prd_counts AS (
        SELECT scope_id, category_id, COUNT(*) AS prd_links,
               COUNT(DISTINCT productid) AS unique_part_types
        FROM scoped_prd GROUP BY scope_id, category_id
    ), category_articles AS (
        SELECT DISTINCT p.nodeid AS category_id, l.supplierid, l.article_key
        FROM links AS l LEFT JOIN prd_links AS p USING (productid, supplierid)
    ), scoped_articles AS (
        SELECT 0 AS scope_id, NULL AS category_id, supplierid, article_key FROM articles
        UNION ALL
        SELECT 1, category_id, supplierid, article_key FROM category_articles
    ), article_counts AS (
        SELECT a.scope_id, a.category_id,
               COUNT(DISTINCT a.supplierid, a.article_key) AS unique_articles,
               COUNT(DISTINCT o.supplierid, o.article_key) AS articles_with_oem,
               COUNT(DISTINCT o.oem_key) AS unique_oem_codes
        FROM scoped_articles AS a LEFT JOIN oems AS o USING (supplierid, article_key)
        GROUP BY a.scope_id, a.category_id
    ), scopes AS (
        SELECT 0 AS scope_id, NULL AS category_id
        UNION DISTINCT
        SELECT scope_id, category_id FROM prd_counts
        UNION DISTINCT
        SELECT scope_id, category_id FROM article_counts
    )
    SELECT s.scope_id, s.category_id,
           COALESCE(p.prd_links, 0) AS prd_links,
           COALESCE(p.unique_part_types, 0) AS unique_part_types,
           COALESCE(a.unique_articles, 0) AS unique_articles,
           COALESCE(a.articles_with_oem, 0) AS articles_with_oem,
           COALESCE(a.unique_oem_codes, 0) AS unique_oem_codes
    FROM scopes AS s
    LEFT JOIN prd_counts AS p ON s.scope_id=p.scope_id AND s.category_id <=> p.category_id
    LEFT JOIN article_counts AS a ON s.scope_id=a.scope_id AND s.category_id <=> a.category_id
    ORDER BY s.scope_id, s.category_id
    LIMIT %s
    """
    with database() as conn:
        manufacturer_id = audit_identity(conn, car_id, kind)
        result = bounded_lookup(conn, sql, (car_id, linkage_type, manufacturer_id, car_id),
                                CATEGORY_LIMIT + 1)
    if result["truncated"]:
        raise HTTPException(503, "Oracle audit category limit exceeded")
    summary, *categories = result["items"]
    summary.pop("category_id")
    for row in (summary, *categories):
        row.pop("scope_id")
        total = row["unique_articles"]
        covered = row["articles_with_oem"]
        row["articles_without_oem"] = total - covered
        row["oem_coverage_percent"] = round(100 * covered / total, 2) if total else None
    return {**audit_response(car_id, kind, manufacturer_id), **summary, "categories": categories}


def audit_page(car_id, kind, offset, limit, selection):
    _, _, linkage_type = audit_source(kind)
    with database() as conn:
        manufacturer_id = audit_identity(conn, car_id, kind)
        result = bounded_lookup(conn, AUDIT_CTES + selection,
                                (car_id, linkage_type, manufacturer_id, offset), limit)
    return {**audit_response(car_id, kind, manufacturer_id), **result,
            "next_offset": offset + limit if result["truncated"] else None}


@app.get("/api/v1/oracle/vehicles/{car_id}/articles", dependencies=[Depends(authorize)])
def audit_articles(kind: CatalogueKind, car_id: int = Path(ge=1),
                   offset: int = Query(default=0, ge=0, le=2147483647),
                   limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    return audit_page(car_id, kind, offset, limit, """
        SELECT supplierid AS supplier_id, CONVERT(article_key USING utf8mb4) AS article_number,
               COUNT(oem_key) AS oem_count
        FROM articles LEFT JOIN oems USING (supplierid, article_key)
        GROUP BY supplierid, article_key
        ORDER BY supplierid, article_key LIMIT %s, %s
    """)


@app.get("/api/v1/oracle/vehicles/{car_id}/oem", dependencies=[Depends(authorize)])
def audit_oem(kind: CatalogueKind, car_id: int = Path(ge=1),
              offset: int = Query(default=0, ge=0, le=2147483647),
              limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    return audit_page(car_id, kind, offset, limit, """
        SELECT CONVERT(oem_key USING utf8mb4) AS oem_number, COUNT(*) AS article_count
        FROM oems GROUP BY oem_key ORDER BY oem_key LIMIT %s, %s
    """)
