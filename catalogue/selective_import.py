"""CarPot Catalogue selective, resumable importer (Windows -> isolated Railway staging).

Local MySQL is read-only. No 50-GiB export. Only known, verified tables.
Uses keyset pagination, bounded batches and atomic progress checkpoints.
"""
import argparse
import json
import os
import pathlib
import time

import pymysql

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / ".import_state"
BATCH_MAX = 1000
STAGING_MAX_MIB = 3500
JOBS = ("manufacturers", "models", "volvo-oem")


def connection(prefix, database):
    return pymysql.connect(
        host=os.getenv(prefix + "_HOST", "127.0.0.1"),
        port=int(os.getenv(prefix + "_PORT", "3306")),
        user=os.environ[prefix + "_USER"],
        password=os.getenv(prefix + "_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=180 if prefix == "SOURCE" else 60,
        write_timeout=60,
        autocommit=True if prefix == "SOURCE" else False,
    )


def checkpoint_path(job):
    return STATE / (job + ".json")


def load_checkpoint(job):
    path = checkpoint_path(job)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_checkpoint(job, position, processed):
    STATE.mkdir(parents=True, exist_ok=True)
    payload = {"job": job, "position": position, "processed": processed}
    destination = checkpoint_path(job)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, destination)


def fetch_batch(source, job, position, n):
    with source.cursor() as cur:
        if job == "manufacturers":
            cur.execute(
                """SELECT id, description, fulldescription
                   FROM manufacturers
                   WHERE id > %s ORDER BY id LIMIT %s""",
                (int(position[0]) if position else 0, n),
            )
        elif job == "models":
            cur.execute(
                """SELECT id, manufacturerid, description, constructioninterval
                   FROM models
                   WHERE id > %s ORDER BY id LIMIT %s""",
                (int(position[0]) if position else 0, n),
            )
        else:
            # Existing local index manufacturerId narrows the OEM query to Volvo.
            # Keyset enables deterministic resume even after network interruptions.
            if position:
                cur.execute(
                    """SELECT oe.supplierId AS supplier_id,
                              oe.DataSupplierArticleNumber AS article_number,
                              oe.manufacturerId AS manufacturer_id,
                              oe.OENbr AS oem_number,
                              a.NormalizedDescription AS name_source
                       FROM article_oe oe
                       JOIN articles a
                         ON a.supplierId=oe.supplierId
                        AND a.DataSupplierArticleNumber=oe.DataSupplierArticleNumber
                       WHERE oe.manufacturerId=120
                         AND (oe.supplierId, oe.DataSupplierArticleNumber, oe.OENbr)
                             > (%s, %s, %s)
                       ORDER BY oe.supplierId, oe.DataSupplierArticleNumber, oe.OENbr
                       LIMIT %s""",
                    (*position, n),
                )
            else:
                cur.execute(
                    """SELECT oe.supplierId AS supplier_id,
                              oe.DataSupplierArticleNumber AS article_number,
                              oe.manufacturerId AS manufacturer_id,
                              oe.OENbr AS oem_number,
                              a.NormalizedDescription AS name_source
                       FROM article_oe oe
                       JOIN articles a
                         ON a.supplierId=oe.supplierId
                        AND a.DataSupplierArticleNumber=oe.DataSupplierArticleNumber
                       WHERE oe.manufacturerId=120
                       ORDER BY oe.supplierId, oe.DataSupplierArticleNumber, oe.OENbr
                       LIMIT %s""",
                    (n,),
                )
        return cur.fetchall()


def last_position(job, row):
    if job in ("manufacturers", "models"):
        return [int(row["id"])]
    return [int(row["supplier_id"]), str(row["article_number"]), str(row["oem_number"])]


def check_target(target, job):
    with target.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
        info = cur.fetchone()
        if info["db"] != os.environ["DEST_DATABASE"]:
            raise RuntimeError("Unexpected target database")
        required = {
            "manufacturers": ["catalogue_manufacturers"],
            "models": ["catalogue_models"],
            "volvo-oem": ["catalogue_parts", "catalogue_oem"],
        }[job]
        for table in required:
            cur.execute("SHOW TABLES LIKE %s", (table,))
            if cur.fetchone() is None:
                raise RuntimeError("Missing staging table: " + table)
        print("Railway target confirmed:", info["db"], info["version"], flush=True)


def check_space(target):
    with target.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(SUM(data_length+index_length), 0)/1024/1024 AS mib
               FROM information_schema.tables WHERE table_schema=DATABASE()"""
        )
        mib = float(cur.fetchone()["mib"])
    if mib >= STAGING_MAX_MIB:
        raise RuntimeError("Stopping: estimated staging tables exceed 3500 MiB")
    return mib


def transfer(target, job, rows):
    with target.cursor() as cur:
        if job == "manufacturers":
            cur.executemany(
                """INSERT INTO catalogue_manufacturers(id,name_source,full_name_source)
                   VALUES (%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                       name_source=VALUES(name_source),
                       full_name_source=VALUES(full_name_source)""",
                [(r["id"],r["description"],r["fulldescription"]) for r in rows],
            )
        elif job == "models":
            cur.executemany(
                """INSERT INTO catalogue_models
                       (id,manufacturer_id,name_source,production_interval)
                   VALUES (%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                       manufacturer_id=VALUES(manufacturer_id),
                       name_source=VALUES(name_source),
                       production_interval=VALUES(production_interval)""",
                [(r["id"],r["manufacturerid"],r["description"],r["constructioninterval"]) for r in rows],
            )
        else:
            parts = {
                (r["supplier_id"], r["article_number"]): r["name_source"]
                for r in rows
            }
            cur.executemany(
                """INSERT INTO catalogue_parts(supplier_id, article_number, name_source)
                   VALUES (%s,%s,%s)
                   ON DUPLICATE KEY UPDATE name_source=VALUES(name_source)""",
                [(sid, article, name) for (sid,article), name in parts.items()],
            )
            cur.executemany(
                """INSERT IGNORE INTO catalogue_oem
                       (supplier_id,article_number,oem_manufacturer_id,oem_number)
                   VALUES (%s,%s,%s,%s)""",
                [(r["supplier_id"],r["article_number"],r["manufacturer_id"],r["oem_number"])
                 for r in rows],
            )


def main():
    parser = argparse.ArgumentParser(description="Read-only-source CarPot Catalogue staging importer")
    parser.add_argument("--job", choices=JOBS, required=True)
    parser.add_argument("--max-rows", type=int, default=1000,
                        help="Maximum source records processed this run, 1–20000")
    parser.add_argument("--batch-size", type=int, default=250,
                        help="Rows per transaction, 1–1000")
    parser.add_argument("--confirm-staging", action="store_true",
                        help="Confirm destination is the isolated Railway catalogue-staging")
    args = parser.parse_args()
    if not args.confirm_staging:
        parser.error("--confirm-staging is required")
    if not 1 <= args.batch_size <= BATCH_MAX or not 1 <= args.max_rows <= 20000:
        parser.error("Limits: batch-size 1..1000; max-rows 1..20000")
    if os.getenv("DEST_DATABASE") not in ("railway", "catalogue"):
        parser.error("Unexpected DEST_DATABASE")
    if os.getenv("DEST_PORT") == os.getenv("SOURCE_PORT", "3306"):
        parser.error("Source and destination must use distinct ports")
    if os.getenv("DEST_HOST") not in ("127.0.0.1", "localhost"):
        parser.error("Destination must use local Railway SSH tunnel")
    STATE.mkdir(parents=True, exist_ok=True)
    lock_path = STATE / (args.job + ".lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SystemExit("Import lock exists; confirm no other importer is running before removing it")
    os.close(lock_fd)
    try:
        state = load_checkpoint(args.job)
        position = state["position"] if state else None
        cumulative = int(state["processed"]) if state else 0
        print(f"Starting {args.job}; resume position={position}; processed before={cumulative}", flush=True)
        with connection("SOURCE", "td1q2018") as source:
            with connection("DEST", os.environ["DEST_DATABASE"]) as target:
                check_target(target, args.job)
                remaining = args.max_rows
                total_this_run = 0
                while remaining > 0:
                    used_mib = check_space(target)
                    amount = min(args.batch_size, remaining)
                    start = time.monotonic()
                    records = fetch_batch(source, args.job, position, amount)
                    if not records:
                        print("Source exhausted for this job.", flush=True)
                        break
                    next_position = last_position(args.job, records[-1])
                    try:
                        transfer(target, args.job, records)
                        target.commit()
                    except Exception:
                        target.rollback()
                        raise
                    cumulative += len(records)
                    total_this_run += len(records)
                    position = next_position
                    save_checkpoint(args.job, position, cumulative)
                    remaining -= len(records)
                    print(f"Committed {total_this_run}/{args.max_rows} this run; "
                          f"checkpoint={position}; DB≈{used_mib:.1f} MiB; "
                          f"batch={time.monotonic()-start:.1f}s", flush=True)
                print(f"SUCCESS {args.job}: processed {total_this_run} rows this run", flush=True)
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
