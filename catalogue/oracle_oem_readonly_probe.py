"""CarPot Oracle OEM preflight. Read-only, bounded, indexed requests only.

Deliberately excludes incomplete article_li and article_links tables.
Connect only through a localhost SSH tunnel to the Oracle MySQL server.
"""
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

TABLES = ("manufacturers", "models", "passanger_cars", "prd",
          "articles", "article_oe", "article_cross", "passanger_car_pds")
DEFERRED = ("article_li", "article_links")
LIMIT = 20


def prefix_index(indexes, table, wanted):
    target = tuple(s.casefold() for s in wanted)
    return any(tuple(x.casefold() for x in cols[:len(target)]) == target
               for cols in indexes.get(table, {}).values())


def colname(columns, table, requested):
    return {c.casefold(): c for c in columns.get(table, [])}.get(requested.casefold())


def quote(name):
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name):
        raise ValueError("Refusing unsafe SQL identifier")
    return chr(96) + name + chr(96)


def readiness(columns, indexes):
    return {
        "oem_lookup": (
            all(colname(columns, "article_oe", c) for c in
                ("supplierId", "DataSupplierArticleNumber", "manufacturerId", "OENbr"))
            and prefix_index(indexes, "article_oe", ("supplierId", "DataSupplierArticleNumber"))
        ),
        "cross_lookup": (
            all(colname(columns, "article_cross", c) for c in
                ("SupplierId", "PartsDataSupplierArticleNumber"))
            and prefix_index(indexes, "article_cross",
                             ("SupplierId", "PartsDataSupplierArticleNumber"))
        ),
        "car_prd_lookup": (
            all(colname(columns, "passanger_car_pds", c) for c in
                ("passangercarid", "productid", "supplierid"))
            and prefix_index(indexes, "passanger_car_pds", ("passangercarid",))
        ),
        "full_fitment_verified": False,
    }


def schema_metadata(conn, database):
    placeholders = ",".join(["%s"] * len(TABLES))
    where = " WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (" + placeholders + ")"
    params = (database, *TABLES)
    with conn.cursor() as c:
        c.execute("SELECT TABLE_NAME,TABLE_ROWS,DATA_LENGTH,INDEX_LENGTH "
                  "FROM information_schema.TABLES" + where, params)
        sizes = {r["TABLE_NAME"]: {
            "approximate_rows": int(r["TABLE_ROWS"] or 0),
            "approximate_data_mib": round(int(r["DATA_LENGTH"] or 0)/1048576, 1),
            "approximate_index_mib": round(int(r["INDEX_LENGTH"] or 0)/1048576, 1)}
            for r in c.fetchall()}
        c.execute("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS"
                  + where + " ORDER BY TABLE_NAME,ORDINAL_POSITION", params)
        columns = {}
        for r in c.fetchall():
            columns.setdefault(r["TABLE_NAME"], []).append(r["COLUMN_NAME"])
        c.execute("SELECT TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME "
                  "FROM information_schema.STATISTICS" + where +
                  " ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX", params)
        indexes = {}
        for r in c.fetchall():
            indexes.setdefault(r["TABLE_NAME"], {}).setdefault(
                r["INDEX_NAME"], []).append(r["COLUMN_NAME"])
    return sizes, columns, indexes


def safe_query(conn, sql, params):
    with conn.cursor() as c:
        c.execute("EXPLAIN " + sql, params)
        plans = c.fetchall()
        if not plans or any(
            not p.get("key") or str(p.get("type", "")).upper() == "ALL"
            or int(p.get("rows") or 0) > 20000 for p in plans
        ):
            raise RuntimeError("STOP: no safe indexed query plan")
        c.execute(sql, params)
        return {"used_indexes": [p["key"] for p in plans],
                "estimated_examined": [int(p.get("rows") or 0) for p in plans],
                "sample": c.fetchall()}


def run_probe(conn, mode, args, columns, ready):
    if mode == "preflight":
        return {"status": "metadata_only"}
    if mode == "prd":
        if not ready["car_prd_lookup"]:
            return {"status": "skipped_missing_columns_or_index"}
        table = "passanger_car_pds"
        c = lambda key: quote(colname(columns, table, key))
        sql = ("SELECT " + c("productid") + " AS product_id," +
               c("supplierid") + " AS supplier_id FROM " + quote(table) +
               " WHERE " + c("passangercarid") + "=%s LIMIT " + str(LIMIT))
        return safe_query(conn, sql, (args.car_id,))
    if not ready["oem_lookup"]:
        return {"status": "skipped_missing_columns_or_index"}
    table = "article_oe"
    c = lambda key: quote(colname(columns, table, key))
    sql = ("SELECT " + c("OENbr") + " AS oem_number FROM " + quote(table) +
           " WHERE " + c("supplierId") + "=%s AND " +
           c("DataSupplierArticleNumber") + "=%s AND " +
           c("manufacturerId") + "=%s LIMIT " + str(LIMIT))
    return safe_query(conn, sql, (args.supplier_id, args.article_number, args.maker_id))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("preflight", "prd", "oem"), default="preflight")
    ap.add_argument("--car-id", type=int)
    ap.add_argument("--supplier-id", type=int)
    ap.add_argument("--article-number")
    ap.add_argument("--maker-id", type=int)
    ap.add_argument("--output", default="oracle-oem-audit")
    a = ap.parse_args()
    if a.mode == "prd" and (a.car_id is None or a.car_id <= 0):
        ap.error("prd requires --car-id > 0")
    if a.mode == "oem" and (
        not a.supplier_id or a.supplier_id <= 0 or
        not a.maker_id or a.maker_id <= 0 or
        not a.article_number or len(a.article_number) > 64 or
        re.search(r"[\x00-\x1f]", a.article_number)
    ):
        ap.error("oem requires valid supplier ID, article number, maker ID")

    if os.getenv("ORACLE_MYSQL_HOST", "127.0.0.1") not in ("127.0.0.1", "localhost"):
        raise SystemExit("STOP: use a localhost SSH tunnel to Oracle MySQL")
    needed = ("ORACLE_MYSQL_PORT", "ORACLE_MYSQL_USER",
              "ORACLE_MYSQL_PASSWORD", "ORACLE_MYSQL_DATABASE")
    if any(key not in os.environ for key in needed):
        raise SystemExit("STOP: missing ORACLE_MYSQL_* credentials/port")
    db = os.environ["ORACLE_MYSQL_DATABASE"]
    if db != "td1q2018":
        raise SystemExit("STOP: only expected td1q2018 database is permitted")

    import pymysql
    cn = pymysql.connect(
        host=os.getenv("ORACLE_MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ["ORACLE_MYSQL_PORT"]),
        user=os.environ["ORACLE_MYSQL_USER"],
        password=os.environ["ORACLE_MYSQL_PASSWORD"], database=db,
        autocommit=False, charset="utf8mb4", connect_timeout=5,
        read_timeout=8, write_timeout=5,
        cursorclass=pymysql.cursors.DictCursor)
    try:
        with cn.cursor() as c:
            c.execute("SET SESSION TRANSACTION READ ONLY")
            c.execute("SET SESSION max_execution_time=3000")
            c.execute("SELECT DATABASE() AS db, @@transaction_read_only AS readonly")
            check = c.fetchone()
            if check["db"] != db or int(check["readonly"]) != 1:
                raise RuntimeError("STOP: database/read-only state mismatch")
        sizes, cols, idx = schema_metadata(cn, db)
        ready = readiness(cols, idx)
        result = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "database": db, "mode": a.mode, "scope": "read_only",
            "unfinished_tables_not_queried": list(DEFERRED),
            "tables": sizes, "columns": cols, "indexes": idx,
            "capabilities": ready,
            "result": run_probe(cn, a.mode, a, cols, ready),
            "notice": "TABLE_ROWS are InnoDB estimates, not exact counts. Fitment not verified."
        }
        dest_dir = Path(a.output)
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = "oracle-oem-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
        dest = dest_dir / name
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")
        print("Saved read-only report:", dest)
        print("Ready:", ", ".join(k for k, v in ready.items() if v) or "none")
        print("No use of article_li or article_links; no database writes.")
    finally:
        cn.rollback()
        cn.close()


if __name__ == "__main__":
    main()
