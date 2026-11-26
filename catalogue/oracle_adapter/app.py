"""Internal, read-only Oracle MySQL catalogue adapter."""
from contextlib import contextmanager
import logging
from time import monotonic
import os
import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query

app = FastAPI(title="CarPot Oracle Catalogue Adapter", version="0.4.1", docs_url=None, redoc_url=None)

logger = logging.getLogger("carpot.oracle_adapter")
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
def database(operation="catalogue"):
    started = monotonic()
    settings = require_database_settings()
    try:
        import pymysql
        connection = pymysql.connect(**settings, charset="utf8mb4", autocommit=False,
                                     connect_timeout=3, read_timeout=5, write_timeout=3,
                                     cursorclass=pymysql.cursors.DictCursor)
    except Exception as error:
        log_database_error(operation, "connect", error, started)
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
        except Exception as error:
            log_database_error(operation, "query", error, started)
            raise HTTPException(status_code=503, detail="Catalogue query unavailable") from None
    finally:
        try:
            connection.rollback()
        except Exception as error:
            log_database_error(operation, "rollback", error, started)
        finally:
            connection.close()


def log_database_error(operation, stage, error, started):
    code = error.args[0] if error.args and type(error.args[0]) is int else None
    logger.warning("oracle_db_failure operation=%s stage=%s error=%s mysql_errno=%s elapsed_ms=%d",
                   operation, stage, type(error).__name__, code, (monotonic() - started) * 1000)



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
    return {"status": "ok", "service": "oracle-catalogue-adapter",
            "version": app.version, "source_verified_live": False}


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
        return (*pds_source(kind), 2)
    # The Oracle schema's commercial linkage type must be confirmed on the
    # source before it can be enabled. Passenger linkage type is reserved.
    value = os.getenv("ORACLE_COMMERCIAL_LINKAGE_TYPE", "")
    if not value.isascii() or not value.isdecimal() or len(value) > 5:
        logger.warning("oracle_commercial_linkage_missing")
        raise HTTPException(503, "Commercial linkage type not configured")
    linkage_type = int(value)
    if not 1 <= linkage_type <= 65535 or linkage_type == 2:
        logger.warning("oracle_commercial_linkage_invalid")
        raise HTTPException(503, "Invalid commercial linkage type")
    return (*pds_source(kind), linkage_type)


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


# Full-read-only catalogue inspection. Source names are preserved, not translated
# or treated as approved CarPot taxonomy. All pages have deterministic ordering.
def pds_source(kind):
    return (("passanger_car_pds", "passangercarid") if kind == "passenger"
            else ("commercial_vehicle_pds", "commertialvehicleid"))


def source_page(car_id, kind, offset, limit, sql):
    with database() as conn:
        manufacturer_id = audit_identity(conn, car_id, kind)
        result = bounded_lookup(conn, sql, (car_id, offset), limit)
    return {**audit_response(car_id, kind, manufacturer_id), **result,
            "next_offset": offset + limit if result["truncated"] else None}


@app.get("/api/v1/oracle/vehicles/{car_id}/prd-page", dependencies=[Depends(authorize)])
def vehicle_prd_page(kind: CatalogueKind, car_id: int = Path(ge=1),
                     offset: int = Query(default=0, ge=0, le=2147483647),
                     limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    table, column = pds_source(kind)
    return source_page(car_id, kind, offset, limit, f"""
        SELECT DISTINCT nodeid AS node_id, productid AS product_id, supplierid AS supplier_id
        FROM {table} FORCE INDEX (PRIMARY) WHERE {column}=%s
        ORDER BY node_id, product_id, supplier_id LIMIT %s, %s
    """)


@app.get("/api/v1/oracle/vehicles/{car_id}/products", dependencies=[Depends(authorize)])
def vehicle_products(kind: CatalogueKind, car_id: int = Path(ge=1),
                     offset: int = Query(default=0, ge=0, le=2147483647),
                     limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    table, column = pds_source(kind)
    return source_page(car_id, kind, offset, limit, f"""
        SELECT DISTINCT p.nodeid AS node_id, p.productid AS product_id,
               r.description AS source_name, r.normalizeddescription AS normalized_name,
               r.assemblygroupdescription AS assembly_group, r.usagedescription AS usage_description
        FROM {table} AS p FORCE INDEX (PRIMARY)
        LEFT JOIN prd AS r ON r.id=p.productid
        WHERE p.{column}=%s
        ORDER BY node_id, product_id, source_name, normalized_name, assembly_group,
                 usage_description LIMIT %s, %s
    """)


@app.get("/api/v1/oracle/vehicles/{car_id}/categories", dependencies=[Depends(authorize)])
def vehicle_categories(kind: CatalogueKind, car_id: int = Path(ge=1),
                       offset: int = Query(default=0, ge=0, le=2147483647),
                       limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    table, column = pds_source(kind)
    result = source_page(car_id, kind, offset, limit, f"""
        SELECT p.nodeid AS node_id, r.assemblygroupdescription AS assembly_group,
               COUNT(DISTINCT p.productid) AS product_count
        FROM {table} AS p FORCE INDEX (PRIMARY)
        LEFT JOIN prd AS r ON r.id=p.productid
        WHERE p.{column}=%s
        GROUP BY p.nodeid, r.assemblygroupdescription
        ORDER BY node_id, assembly_group LIMIT %s, %s
    """)
    return {**result, "category_basis": "prd_assembly_group", "tree_verified": False}


@app.get("/api/v1/oracle/vehicles/{car_id}/part-articles", dependencies=[Depends(authorize)])
def vehicle_part_articles(kind: CatalogueKind, car_id: int = Path(ge=1),
                          product_id: int = Query(ge=1, le=2147483647),
                          offset: int = Query(default=0, ge=0, le=2147483647),
                          limit: int = Query(default=20, ge=1, le=ROW_LIMIT)):
    _, _, linkage_type = audit_source(kind)
    # Restrict the expensive article/OEM join to one source part type. A null
    # OEM is an observed lack of a cross-reference, not proof no OE part exists.
    sql = """
        WITH links AS (
            SELECT DISTINCT supplierid, CAST(datasupplierarticlenumber AS BINARY) AS article_key,
                   datasupplierarticlenumber AS article_number
            FROM article_links FORCE INDEX (linkageid)
            WHERE linkageid=%s AND linkagetypeid=%s AND productid=%s
              AND supplierid>0 AND datasupplierarticlenumber<>''
        )
        SELECT DISTINCT l.supplierid AS supplier_id,
               CONVERT(l.article_key USING utf8mb4) AS article_number,
               s.description AS supplier_name,
               CONVERT(CAST(o.OENbr AS BINARY) USING utf8mb4) AS oem_number,
               l.article_key AS sort_article,
               CAST(o.OENbr AS BINARY) AS sort_oem
        FROM links AS l
        LEFT JOIN suppliers AS s ON s.id=l.supplierid
        LEFT JOIN article_oe AS o FORCE INDEX (supplierid)
          ON o.supplierid=l.supplierid
          AND o.datasupplierarticlenumber=l.article_number
          AND CAST(o.datasupplierarticlenumber AS BINARY)=l.article_key
          AND o.manufacturerId=%s AND o.OENbr<>''
        ORDER BY supplier_id, sort_article, sort_oem, supplier_name LIMIT %s, %s
    """
    with database() as conn:
        manufacturer_id = audit_identity(conn, car_id, kind)
        result = bounded_lookup(conn, sql, (car_id, linkage_type, product_id, manufacturer_id, offset), limit)
    for item in result["items"]:
        item.pop("sort_article", None)
        item.pop("sort_oem", None)
    return {**audit_response(car_id, kind, manufacturer_id), **result, "product_id": product_id,
            "next_offset": offset + limit if result["truncated"] else None}


@app.get("/api/v1/oracle/vehicles/manufacturer-directory", dependencies=[Depends(authorize)])
def manufacturer_directory(kind: CatalogueKind, name: str = Query("", max_length=100),
                           after: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=ROW_LIMIT)):
    flag = "ispassengercar" if kind == "passenger" else "iscommercialvehicle"
    # Escape LIKE metacharacters before applying the optional name search.
    term = name.strip().replace("=", "==").replace("%", "=%").replace("_", "=_")
    with database("manufacturer_directory") as conn:
        result = bounded_lookup(conn, f"""
            SELECT DISTINCT id, description AS name FROM manufacturers
            WHERE {flag}='True' AND id>%s AND description IS NOT NULL AND description!=''
              AND description LIKE CONCAT('%%', %s, '%%') ESCAPE '='
            ORDER BY id LIMIT %s
        """, (after, term), limit)
    return dict(source="oracle", kind=kind, **result, vehicle_identity_only=True,
                fitment_verified=False,
                next_after=result["items"][-1]["id"] if result["truncated"] else None)


def graph_identity(conn, kind, car_id):
    table = "passanger_cars" if kind == "passenger" else "commercial_vehicles"
    flag = "ispassengercar" if kind == "passenger" else "iscommercialvehicle"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT v.modelid AS model_id, m.manufacturerid AS manufacturer_id,
                   v.description, v.constructioninterval AS construction_interval
            FROM {table} AS v FORCE INDEX (PRIMARY)
            LEFT JOIN models AS m ON m.id=v.modelid AND m.{flag}='True'
            WHERE v.id=%s LIMIT 2
        """, (car_id,))
        rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) != 1 or not rows[0]["manufacturer_id"] or not rows[0]["model_id"]:
        raise HTTPException(503, "Ambiguous catalogue modification")
    return rows[0]


def graph_rows(conn, sql, args, *, stage, started, size=500):
    # Pages are read on the same read-only transaction. An interrupted read
    # fails the graph instead of returning a successful truncated result.
    offset = 0
    while True:
        if monotonic() - started > 18:
            logger.warning("oracle_graph_deadline stage=%s", stage)
            raise HTTPException(503, "Catalogue deadline exceeded")
        page = bounded_lookup(conn, sql, (*args, offset), size)
        yield from page["items"]
        if not page["truncated"]:
            return
        offset += size


def graph_links(conn, car_id, linkage_type, started):
    sql = """
        SELECT DISTINCT productid AS product_id, supplierid AS supplier_id,
               CAST(datasupplierarticlenumber AS BINARY) AS article_key
        FROM article_links FORCE INDEX (linkageid)
        WHERE linkageid=%s AND linkagetypeid=%s AND productid>0 AND supplierid>0
          AND datasupplierarticlenumber<>''
        ORDER BY product_id, supplier_id, article_key LIMIT %s, %s
    """
    return graph_rows(conn, sql, (car_id, linkage_type), stage="article_links", started=started)


def graph_enrichment(conn, article_keys, manufacturer_id, started):
    for offset in range(0, len(article_keys), 100):
        if monotonic() - started > 18:
            logger.warning("oracle_graph_deadline stage=article_oe")
            raise HTTPException(503, "Catalogue deadline exceeded")
        batch = article_keys[offset:offset + 100]
        pairs = ",".join(["(%s,%s)"] * len(batch))
        supplier_ids = sorted({key[0] for key in batch})
        suppliers = ",".join(["%s"] * len(supplier_ids))
        with conn.cursor() as cur:
            cur.execute(f"SELECT DISTINCT id, description FROM suppliers WHERE id IN ({suppliers})", supplier_ids)
            names = {}
            ambiguous = set()
            for row in cur.fetchall():
                sid = row["id"]
                if sid in names:
                    ambiguous.add(sid)
                names[sid] = row["description"]
            cur.execute(f"""
                SELECT DISTINCT supplierid AS supplier_id,
                       CAST(datasupplierarticlenumber AS BINARY) AS article_key,
                       CAST(OENbr AS BINARY) AS oem_key
                FROM article_oe FORCE INDEX (supplierid)
                WHERE (supplierid,datasupplierarticlenumber) IN ({pairs})
                  AND manufacturerId=%s AND OENbr<>''
            """, (*(value for key in batch for value in key), manufacturer_id))
            refs = {}
            for row in cur.fetchall():
                key = (row["supplier_id"], row["article_key"].decode("utf-8"))
                refs.setdefault(key, set()).add(row["oem_key"].decode("utf-8"))
        for sid, number in batch:
            yield [sid, number, names.get(sid) if sid not in ambiguous else None,
                   sorted(refs.get((sid, number), ()))]


def graph_products(conn, kind, car_id, products, started):
    table, column = pds_source(kind)
    sql = f"""
        SELECT DISTINCT nodeid AS node_id, productid AS product_id FROM {table}
        FORCE INDEX (PRIMARY) WHERE {column}=%s AND productid>0
        ORDER BY product_id, node_id LIMIT %s, %s
    """
    nodes = {}
    for row in graph_rows(conn, sql, (car_id,), stage="prd_nodes", started=started):
        linked_nodes = nodes.setdefault(row["product_id"], [])
        if row["node_id"] is not None:
            linked_nodes.append(row["node_id"])
    ids = sorted(nodes.keys() | products)
    for offset in range(0, len(ids), 250):
        batch = ids[offset:offset + 250]
        placeholders = ",".join(["%s"] * len(batch))
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT DISTINCT id, description, normalizeddescription,
                       assemblygroupdescription, usagedescription
                FROM prd WHERE id IN ({placeholders})
                ORDER BY id, description, normalizeddescription, assemblygroupdescription, usagedescription
            """, batch)
            labels = {}
            for row in cur.fetchall():
                labels.setdefault(row["id"], []).append(row)
        for pid in batch:
            yield dict(product_id=pid, node_ids=nodes.get(pid, []), descriptions=labels.get(pid, []))


@app.get("/api/v1/oracle/vehicles/{car_id}/source-graph", dependencies=[Depends(authorize)])
def source_graph(kind: CatalogueKind, car_id: int = Path(ge=1),
                 manufacturer_id: int = Query(gt=0), model_id: int = Query(gt=0)):
    requested = dict(kind=kind, car_id=car_id, manufacturer_id=manufacturer_id, model_id=model_id)
    started = monotonic()
    with database("source_graph_" + kind) as conn:
        identity = graph_identity(conn, kind, car_id)
        if identity is None:
            return dict(identity=requested, status="absent", reason="modification_absent")
        if (identity["manufacturer_id"], identity["model_id"]) != (manufacturer_id, model_id):
            return dict(identity=requested, status="identity_mismatch", reason="source_identity_mismatch")
        _, _, linkage_type = audit_source(kind)
        links = {}
        articles = set()
        for row in graph_links(conn, car_id, linkage_type, started):
            key = (row["supplier_id"], row["article_key"].decode("utf-8"))
            links.setdefault(row["product_id"], []).append(key)
            articles.add(key)
        products = list(graph_products(conn, kind, car_id, set(links), started))
        if not products:
            return dict(identity=requested, status="absent", reason="no_source_parts")
        keys = sorted(articles)
        article_ids = {key: i for i, key in enumerate(keys)}
        return dict(identity=requested, status="available", modification=identity,
                    products=products, articles=list(graph_enrichment(conn, keys, manufacturer_id, started)),
                    links={pid: [article_ids[key] for key in linked] for pid, linked in links.items()})
