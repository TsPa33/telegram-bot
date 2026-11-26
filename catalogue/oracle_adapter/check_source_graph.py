"""Run on the existing Oracle host, with the adapter's own read-only identity."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

import pymysql

HTTP = build_opener(ProxyHandler({}))

CONTROL = (
    ("passenger", 120, 13084, 107555),
    ("commercial", 24, 5539, 8387),
    ("passenger", 16, 290, 21),
)
COLUMNS = {
    "manufacturers": ("id", "description", "ispassengercar", "iscommercialvehicle"),
    "models": ("id", "manufacturerid", "description", "constructioninterval", "ispassengercar", "iscommercialvehicle"),
    "passanger_cars": ("id", "modelid", "description", "constructioninterval"),
    "commercial_vehicles": ("id", "modelid", "description", "constructioninterval"),
    "passanger_car_attributes": ("passangercarid", "attributetype", "displayvalue"),
    "commercial_vehicle_attributes": ("commercialvehicleid", "attributetype", "displayvalue"),
    "passanger_car_pds": ("passangercarid", "nodeid", "productid", "supplierid"),
    "commercial_vehicle_pds": ("commertialvehicleid", "nodeid", "productid", "supplierid"),
    "prd": ("id", "description", "normalizeddescription", "assemblygroupdescription", "usagedescription"),
    "suppliers": ("id", "description"),
    "article_links": ("linkageid", "linkagetypeid", "productid", "supplierid", "datasupplierarticlenumber"),
    "article_oe": ("supplierid", "datasupplierarticlenumber", "manufacturerid", "oenbr"),
    "article_cross": ("supplierid", "partsdatasupplierarticlenumber", "manufacturerid", "oenbr"),
}
INDEXES = {
    ("models", "manufacturerid"): ("manufacturerid",),
    ("passanger_cars", "primary"): ("id",),
    ("passanger_cars", "modelid"): ("modelid",),
    ("commercial_vehicles", "primary"): ("id",),
    ("commercial_vehicles", "modelid"): ("modelid",),
    ("passanger_car_attributes", "passangercarid"): ("passangercarid",),
    ("commercial_vehicle_attributes", "commercialvehicleid"): ("commercialvehicleid",),
    ("passanger_car_pds", "primary"): ("passangercarid",),
    ("commercial_vehicle_pds", "primary"): ("commertialvehicleid", "nodeid", "productid", "supplierid"),
    ("article_links", "linkageid"): ("linkageid",),
    ("article_oe", "supplierid"): ("supplierid", "datasupplierarticlenumber"),
    ("article_cross", "oenbr"): ("oenbr",),
}


def report(label, **data):
    print(json.dumps(dict(check=label, **data), ensure_ascii=False, default=str), flush=True)


def read_env(pid):
    path = Path(f"/proc/{pid}/environ")
    return dict(field.decode().split("=", 1) for field in path.read_bytes().split(b"\0")
                if field.startswith(b"ORACLE_") and b"=" in field)


def query(conn, label, sql, args=()):
    started = monotonic()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, args)
            rows = cursor.fetchall()
    except pymysql.MySQLError as error:
        report(label, ok=False, mysql_errno=error.args[0], elapsed_ms=round((monotonic() - started) * 1000))
        return None
    report(label, ok=True, rows=rows, elapsed_ms=round((monotonic() - started) * 1000))
    return rows


def check_db(env):
    if (env.get("ORACLE_MYSQL_DATABASE") != "td1q2018"
            or env.get("ORACLE_MYSQL_HOST") not in ("127.0.0.1", "localhost")
            or env.get("ORACLE_MYSQL_USER", "").casefold() in ("", "root", "admin")):
        report("db_settings", ok=False)
        return False
    try:
        with pymysql.connect(host=env["ORACLE_MYSQL_HOST"], port=int(env["ORACLE_MYSQL_PORT"]),
                             user=env["ORACLE_MYSQL_USER"], password=env["ORACLE_MYSQL_PASSWORD"],
                             database=env["ORACLE_MYSQL_DATABASE"], charset="utf8mb4",
                             cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                             connect_timeout=3, read_timeout=5, write_timeout=3) as conn:
            return diagnose(conn, env)
    except (KeyError, ValueError, pymysql.MySQLError) as error:
        code = error.args[0] if error.args and type(error.args[0]) is int else None
        report("db_connect_or_session", ok=False, error=type(error).__name__, mysql_errno=code)
        return False


def diagnose(conn, env):
    with conn.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.execute("SET SESSION max_execution_time=3000")
    mode = query(conn, "session", "SELECT VERSION() AS mysql_version, @@transaction_read_only AS ro")
    if not mode or int(mode[0]["ro"]) != 1:
        return False
    ready = True
    for table, columns in COLUMNS.items():
        selected = ", ".join(f"`{column}`" for column in columns)
        ready &= query(conn, f"select_{table}", f"SELECT {selected} FROM `{table}` LIMIT 0") is not None
    tables = (*COLUMNS, "passanger_car_trees", "commercial_vehicle_trees")
    placeholders = ",".join(["%s"] * len(tables))
    query(conn, "category_tree_columns", """
        SELECT table_name, column_name, column_type FROM information_schema.columns
        WHERE table_schema=DATABASE() AND table_name IN ('passanger_car_trees','commercial_vehicle_trees')
        ORDER BY table_name, ordinal_position
    """)
    indexes = query(conn, "indexes", f"""
        SELECT LOWER(table_name) AS tbl, LOWER(index_name) AS idx,
               seq_in_index AS pos, LOWER(column_name) AS col
        FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name IN ({placeholders})
        ORDER BY tbl, idx, pos
    """, tables)
    observed = {}
    for row in indexes or ():
        observed.setdefault((row["tbl"], row["idx"]), []).append(row["col"])
    missing = [f"{table}.{index}" for (table, index), columns in INDEXES.items()
               if tuple(observed.get((table, index), ()))[:len(columns)] != columns]
    report("required_index_prefixes", ok=not missing, missing=missing)
    ready &= not missing

    for kind, maker, model, car in CONTROL:
        vehicle_table = "passanger_cars" if kind == "passenger" else "commercial_vehicles"
        flag = "ispassengercar" if kind == "passenger" else "iscommercialvehicle"
        rows = query(conn, f"identity_{kind}_{car}", f"""
            SELECT c.id AS car_id, c.modelid AS model_id, m.manufacturerid AS manufacturer_id
            FROM {vehicle_table} AS c
            JOIN models AS m ON m.id=c.modelid AND m.{flag}='True'
            WHERE c.id=%s AND c.modelid=%s AND m.manufacturerid=%s LIMIT 2
        """, (car, model, maker))
        ready &= bool(rows and len(rows) == 1)

    agreed, votes, ambiguous = commercial_linkage(conn)
    configured = env.get("ORACLE_COMMERCIAL_LINKAGE_TYPE", "")
    report("commercial_linkage", verified_value=agreed,
           configured=int(configured) if configured.isascii() and configured.isdecimal() and len(configured) <= 5 else None,
           matching_witnesses=len(votes), witness_ids=[vote[1] for vote in votes], ambiguous=ambiguous)
    ready &= agreed is not None and 1 <= agreed <= 65535
    for kind, _, _, car in CONTROL:
        linkage = 2 if kind == "passenger" else agreed
        if linkage is None:
            continue
        sql = """
            SELECT DISTINCT productid AS product_id, supplierid AS supplier_id,
                   CAST(datasupplierarticlenumber AS BINARY) AS article_key
            FROM article_links FORCE INDEX (linkageid)
            WHERE linkageid=%s AND linkagetypeid=%s AND productid>0 AND supplierid>0
              AND datasupplierarticlenumber<>''
            ORDER BY product_id, supplier_id, article_key LIMIT 0, 501
        """
        plan = query(conn, f"explain_graph_links_{kind}_{car}", "EXPLAIN " + sql, (car, linkage))
        ready &= bool(plan and any(row.get("key") == "linkageid" for row in plan))
        sample = query(conn, f"sample_graph_links_{kind}_{car}", f"SELECT COUNT(*) AS sampled_links FROM ({sql}) AS scoped",
                       (car, linkage))
        ready &= bool(sample)
    report("diagnostic_result", ready_to_install=ready, verified_commercial_linkage_type=agreed)
    return ready


def commercial_linkage(conn):
    """Find agreeing PDS/article witnesses from separate commercial models."""

    references = query(conn, "commercial_witness_models", """
        SELECT manufacturerid AS manufacturer_id, MIN(id) AS first_model, MAX(id) AS last_model
        FROM models WHERE iscommercialvehicle='True' AND manufacturerid>0
        GROUP BY manufacturerid ORDER BY manufacturerid LIMIT 20
    """)
    if references is None:
        return None, [], True
    control = next(model for kind, _, model, _ in CONTROL if kind == "commercial")
    # Interleave early and late models across makes to include variants with
    # different source coverage. The control model is diagnostic only.
    models = list(dict.fromkeys((control, *(row["last_model"] for row in references),
                                *(row["first_model"] for row in references))))
    started = monotonic()
    votes = []
    checked = set()
    ambiguous = False
    for allow_overlap in (False, True):
        for model in models:
            if monotonic() - started > 45:
                return None, votes, True
            if any(vote[0] == model for vote in votes):
                continue
            collision = "" if allow_overlap else "AND NOT EXISTS (SELECT 1 FROM passanger_cars AS p WHERE p.id=c.id)"
            rows = query(conn, f"commercial_witnesses_{model}_{int(allow_overlap)}", f"""
                SELECT c.id FROM commercial_vehicles AS c FORCE INDEX (modelid)
                WHERE c.modelid=%s {collision} ORDER BY c.id LIMIT 3
            """, (model,))
            if rows is None:
                return None, votes, True
            for row in rows:
                car = row["id"]
                if car in checked:
                    continue
                checked.add(car)
                # A numeric ID can exist in both namespaces. With overlap,
                # count only PDS pairs absent from the passenger PDS namespace.
                exclusion = """
                    AND NOT EXISTS (
                        SELECT 1 FROM passanger_car_pds AS pp FORCE INDEX (PRIMARY)
                        WHERE pp.passangercarid=a.linkageid
                          AND pp.productid=a.productid AND pp.supplierid=a.supplierid
                    )
                """ if allow_overlap else ""
                matched = query(conn, f"commercial_pds_linkage_{car}", f"""
                    SELECT a.linkagetypeid AS linkage_type,
                           COUNT(DISTINCT a.productid, a.supplierid) AS pairs
                    FROM article_links AS a FORCE INDEX (linkageid)
                    STRAIGHT_JOIN commercial_vehicle_pds AS p FORCE INDEX (PRIMARY)
                      ON p.commertialvehicleid=a.linkageid AND p.productid=a.productid
                      AND p.supplierid=a.supplierid
                    WHERE a.linkageid=%s AND a.linkagetypeid<>2 {exclusion}
                    GROUP BY a.linkagetypeid ORDER BY a.linkagetypeid
                """, (car,))
                if matched is None:
                    return None, votes, True
                if len(matched) > 1:
                    ambiguous = True
                    continue
                if matched:
                    votes.append((model, car, matched[0]["linkage_type"]))
                    break
            if len(votes) >= 3:
                break
        if len(votes) >= 2 or ambiguous:
            break
    codes = {vote[2] for vote in votes}
    ambiguous |= len(codes) > 1
    agreed = next(iter(codes)) if len(votes) >= 2 and not ambiguous and len(codes) == 1 else None
    return agreed, votes, ambiguous


def http(env, route, **params):
    started = monotonic()
    try:
        req = Request(f"http://127.0.0.1:8081{route}?{urlencode(params)}",
                      headers={"X-Oracle-Adapter-Key": env["ORACLE_ADAPTER_KEY"], "Accept": "application/json"})
        with HTTP.open(req, timeout=28) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("response size")
            return response.status, json.loads(raw), round((monotonic() - started) * 1000)
    except HTTPError as error:
        return error.code, {}, round((monotonic() - started) * 1000)
    except (KeyError, ValueError, URLError, TimeoutError):
        return None, {}, round((monotonic() - started) * 1000)


def verify(env):
    status, health, elapsed = http(env, "/health")
    ready = status == 200 and health.get("version") == "0.4.1"
    report("health", status=status, version=health.get("version"), elapsed_ms=elapsed)
    status, result, elapsed = http(env, "/api/v1/oracle/oem/by-article",
                                   supplier_id=1, article_number=20064, manufacturer_id=120, limit=20)
    report("legacy_oem_by_article", status=status, items=len(result.get("items", [])), elapsed_ms=elapsed)
    ready &= status == 200
    for kind, maker, model, car in CONTROL:
        prefix = f"/api/v1/oracle/vehicles/{car}/"
        for endpoint in ("audit", "articles", "oem"):
            params = dict(kind=kind, limit=1) if endpoint != "audit" else dict(kind=kind)
            status, data, elapsed = http(env, prefix + endpoint, **params)
            report("route", kind=kind, car_id=car, route=endpoint, status=status, elapsed_ms=elapsed)
            ready &= status == 200 and data.get("source_modification_id") == car and data.get("kind") == kind
        identity = dict(kind=kind, manufacturer_id=maker, model_id=model, car_id=car)
        status, data, elapsed = http(env, prefix + "source-graph", kind=kind, manufacturer_id=maker, model_id=model)
        matched = status == 200 and data.get("identity") == identity and data.get("status") == "available"
        ready &= matched
        result = dict(status=status, graph_status=data.get("status"), elapsed_ms=elapsed)
        if matched:
            products, articles = data["products"], data["articles"]
            product_links = data["links"]
            categories = {label.get("assemblygroupdescription") for p in products for label in p["descriptions"]
                          if label.get("assemblygroupdescription")}
            with_oem = sum(any(articles[idx][3] for idx in product_links.get(str(p["product_id"]), []))
                           for p in products)
            result.update(groups=len(categories), subcategories=None, unique_part_types=len(products),
                          positions=len(products), unique_articles=len(articles),
                          unique_oem=len({code for article in articles for code in article[3]}),
                          positions_with_oem=with_oem, positions_without_oem=len(products) - with_oem)
        report("source_graph", **identity, **result)
    for kind in ("passenger", "commercial"):
        status, data, elapsed = http(env, "/api/v1/oracle/vehicles/manufacturer-directory", kind=kind, limit=5)
        report("manufacturer_directory", kind=kind, status=status, elapsed_ms=elapsed)
        ready &= status == 200 and data.get("kind") == kind and bool(data.get("items"))
    report("verify_result", ok=ready)
    return ready


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("diagnose", "verify"))
    parser.add_argument("pid", type=int)
    args = parser.parse_args()
    if args.pid < 2:
        parser.error("A running systemd MainPID is required")
    try:
        env = read_env(args.pid)
        deployed = Path("/opt/carpot/oracle-adapter/app.py")
        report("deployed_file", sha256=hashlib.sha256(deployed.read_bytes()).hexdigest(),
               mtime_epoch=int(deployed.stat().st_mtime))
        passed = check_db(env) if args.mode == "diagnose" else verify(env)
    except (OSError, KeyError, ValueError) as error:
        report("probe_error", error=type(error).__name__)
        passed = False
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
