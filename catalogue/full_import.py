"""Full catalogue article/OEM importer. Local source SELECT-only; staging destination only.

Two jobs, --job articles / --job oem. Each run resumes from a checkpoint
committed atomically in Railway with the data. Does NOT change source indexes.
OEM import is refused unless a suitable source index exists.
"""
import argparse
import os
import time
from collections import defaultdict

import pymysql

REQUIRED_INDEX_PREFIX = {
    "articles": ("supplierId", "DataSupplierArticleNumber"),
    "article_oe": ("supplierId", "DataSupplierArticleNumber", "manufacturerId", "OENbr"),
}

def connect(prefix, database, autocommit):
    return pymysql.connect(
        host=os.environ.get(prefix + "_HOST", "127.0.0.1"),
        port=int(os.environ.get(prefix + "_PORT", "3306")),
        user=os.environ[prefix + "_USER"],
        password=os.environ.get(prefix + "_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=autocommit, connect_timeout=10,
        read_timeout=180 if prefix == "SOURCE" else 60, write_timeout=60,
    )

def index_report(db, table):
    with db.cursor() as cur:
        cur.execute("SHOW INDEX FROM `" + table + "`")
        entries = cur.fetchall()
    indexes = defaultdict(list)
    for r in entries:
        indexes[r["Key_name"]].append((int(r["Seq_in_index"]), r["Column_name"]))
    return {k: tuple(c for _, c in sorted(v)) for k, v in indexes.items()}

def verify_source_index(source, job):
    table = "articles" if job == "articles" else "article_oe"
    desired = REQUIRED_INDEX_PREFIX[table]
    indexes = index_report(source, table)
    matched = [k for k, cols in indexes.items() if cols[:len(desired)] == desired]
    if not matched:
        print(f"INDEX NOT VERIFIED for {table}. Required prefix: {desired}", flush=True)
        print("Existing indexes:", indexes, flush=True)
        raise SystemExit("Stopped safely. Source DB is unchanged; do not create source indexes without a backup.")
    print(f"Source index validated: {table}.{matched[0]}", flush=True)

def used_mib(db):
    with db.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(data_length+index_length), 0)/1024/1024 AS mib
                       FROM information_schema.tables WHERE table_schema = DATABASE()""")
        return float(cur.fetchone()["mib"])

def checkpoint(db, job):
    with db.cursor() as cur:
        cur.execute("""SELECT last_supplier_id, last_article_number,
                          last_manufacturer_id, last_oem_number, processed
                       FROM catalogue_import_progress WHERE job=%s""", (job,))
        return cur.fetchone()

def fetch(source, job, state, size):
    with source.cursor() as cur:
        if job == "articles":
            last = (state["last_supplier_id"], state["last_article_number"]) if state else (0, "")
            cur.execute(
                """SELECT supplierId, DataSupplierArticleNumber, NormalizedDescription
                   FROM articles
                   WHERE (supplierId, DataSupplierArticleNumber) > (%s,%s)
                   ORDER BY supplierId, DataSupplierArticleNumber LIMIT %s""",
                (*last, size),
            )
        else:
            last = (
                state["last_supplier_id"], state["last_article_number"],
                state["last_manufacturer_id"], state["last_oem_number"]
            ) if state else (0, "", 0, "")
            cur.execute(
                """SELECT supplierId, DataSupplierArticleNumber, manufacturerId, OENbr
                   FROM article_oe
                   WHERE (supplierId, DataSupplierArticleNumber, manufacturerId, OENbr)
                         > (%s,%s,%s,%s)
                   ORDER BY supplierId, DataSupplierArticleNumber, manufacturerId, OENbr
                   LIMIT %s""",
                (*last, size),
            )
        return cur.fetchall()

def transfer(db, job, rows, already):
    last = rows[-1]
    with db.cursor() as cur:
        if job == "articles":
            cur.executemany(
                """INSERT INTO catalogue_parts (supplier_id,article_number,name_source)
                   VALUES (%s,%s,%s)
                   ON DUPLICATE KEY UPDATE name_source=VALUES(name_source)""",
                [(r["supplierId"],r["DataSupplierArticleNumber"],r["NormalizedDescription"]) for r in rows],
            )
            marker = (last["supplierId"], last["DataSupplierArticleNumber"], 0, "")
        else:
            cur.executemany(
                """INSERT IGNORE INTO catalogue_oem
                      (supplier_id,article_number,oem_manufacturer_id,oem_number)
                   VALUES (%s,%s,%s,%s)""",
                [(r["supplierId"],r["DataSupplierArticleNumber"],
                  r["manufacturerId"],r["OENbr"]) for r in rows],
            )
            marker = (last["supplierId"],last["DataSupplierArticleNumber"],
                      last["manufacturerId"],last["OENbr"])
        cur.execute(
            """INSERT INTO catalogue_import_progress
               (job,last_supplier_id,last_article_number,last_manufacturer_id,last_oem_number,processed)
               VALUES (%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
               last_supplier_id=VALUES(last_supplier_id),
               last_article_number=VALUES(last_article_number),
               last_manufacturer_id=VALUES(last_manufacturer_id),
               last_oem_number=VALUES(last_oem_number),
               processed=VALUES(processed)""",
            (job,*marker,already+len(rows)),
        )

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--job",choices=("articles","oem"),required=True)
    p.add_argument("--batch-size",type=int,default=500)
    p.add_argument("--max-rows",type=int,default=20000)
    p.add_argument("--max-db-mib",type=int,default=3000)
    p.add_argument("--confirm-staging",action="store_true")
    p.add_argument("--preflight",action="store_true")
    args=p.parse_args()
    if not args.confirm_staging: p.error("Explicit --confirm-staging required")
    if not 1<=args.batch_size<=1000 or not 1<=args.max_rows<=200000:
        p.error("batch-size 1..1000; max-rows 1..200000")
    if not 100<=args.max_db_mib<=3500: p.error("max-db-mib 100..3500")
    if os.getenv("DEST_DATABASE") not in ("railway","catalogue"):
        p.error("Only isolated Railway catalogue staging target allowed")
    if os.getenv("DEST_HOST") not in ("127.0.0.1","localhost"):
        p.error("Connect over a local SSH tunnel")
    if os.getenv("DEST_PORT")==os.getenv("SOURCE_PORT","3306"):
        p.error("Destination port must differ from local MySQL")
    source=connect("SOURCE","td1q2018",True)
    try:
        verify_source_index(source,args.job)
        if args.preflight:
            print("PREFLIGHT OK: matching source index exists, no data written",flush=True)
            return
        dest=connect("DEST",os.environ["DEST_DATABASE"],False)
        try:
            with dest.cursor() as cur:
                cur.execute("SHOW TABLES LIKE 'catalogue_import_progress'")
                if not cur.fetchone(): raise SystemExit("Missing staging checkpoint table")
                if args.job=="oem":
                    cur.execute("SHOW TABLES LIKE 'catalogue_oem'")
                else:
                    cur.execute("SHOW TABLES LIKE 'catalogue_parts'")
                if not cur.fetchone(): raise SystemExit("Missing target table")
            state=checkpoint(dest,args.job)
            count=int(state["processed"]) if state else 0
            print(f"Starting {args.job}, committed before={count}",flush=True)
            done=0
            while done<args.max_rows:
                size=used_mib(dest)
                if size>=args.max_db_mib:
                    raise SystemExit(f"Disk guard stopped import: estimated DB={size:.1f} MiB")
                begin=time.monotonic()
                rows=fetch(source,args.job,state,min(args.batch_size,args.max_rows-done))
                if not rows:
                    print("SOURCE EXHAUSTED: job fully scanned",flush=True)
                    break
                try:
                    transfer(dest,args.job,rows,count)
                    dest.commit()
                except BaseException:
                    dest.rollback()
                    raise
                count+=len(rows)
                done+=len(rows)
                state=checkpoint(dest,args.job)
                print(f"COMMITTED {done}/{args.max_rows} this run | total {count} | "
                      f"DB≈{size:.1f} MiB | {time.monotonic()-begin:.1f}s",flush=True)
            print(f"OK: {args.job} processed {done} source rows this run",flush=True)
        finally:
            dest.close()
    finally:
        source.close()

if __name__=="__main__":
    main()
