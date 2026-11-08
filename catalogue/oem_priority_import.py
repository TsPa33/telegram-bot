"""Priority OEM importer: Volvo first, then 29 selected makes.

Read-only local source, existing manufacturerId index, Railway staging only.
A completed brand is checkpointed. Interrupted brands are reread on restart;
destination primary keys prevent duplicate OEMs.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from itertools import islice
from pathlib import Path
from time import monotonic

import pymysql

MANIFEST = Path(__file__).with_name("oem_priority_30.json")
LOCK = "carpot_oem_priority_v1"


def norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    return re.sub(r"[^a-z0-9а-яіїєґ]+", "",
                  "".join(x for x in text if not unicodedata.combining(x)))


def db(prefix, database, source=False):
    conn = pymysql.connect(
        host=os.getenv(prefix + "_HOST", "127.0.0.1"),
        port=int(os.getenv(prefix + "_PORT", "3306")),
        user=os.environ[prefix + "_USER"],
        password=os.getenv(prefix + "_PASSWORD", ""),
        database=database, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10, read_timeout=180 if source else 60,
        write_timeout=60, autocommit=source)
    if source:
        # SOURCE connection only. Session-level timeout has no persistent effect
        # on the local server and does not modify the original database.
        with conn.cursor() as cursor:
            cursor.execute("SELECT @@SESSION.max_execution_time AS limit_ms")
            prior_ms = int(cursor.fetchone()["limit_ms"])
            if prior_ms:
                cursor.execute("SET SESSION max_execution_time = 0")
                print(f"Local source SELECT time limit: {prior_ms} ms -> "
                      "disabled for this importer connection only", flush=True)
    return conn


def resolve(source, selected):
    with source.cursor() as cur:
        cur.execute("SHOW INDEX FROM article_oe")
        indexes = cur.fetchall()
        cur.execute("SELECT id,description FROM manufacturers")
        manufacturers = cur.fetchall()
    matched = [r["Key_name"] for r in indexes
               if str(r["Column_name"]).casefold() == "manufacturerid"
               and int(r["Seq_in_index"]) == 1]
    if not matched:
        raise RuntimeError("No suitable manufacturerId source index")
    index = matched[0]
    if not re.fullmatch(r"[A-Za-z0-9_]+",index):
        raise RuntimeError("Unsupported source index name")
    lookup = {}
    for m in manufacturers:
        lookup.setdefault(norm(m["description"]), []).append(m)
    resolved = []
    for b in selected:
        choices = {}
        for name in b["aliases"]:
            for row in lookup.get(norm(name), []):
                choices[int(row["id"])] = row["description"]
        if b.get("confirmed_source_id") is not None:
            choices = {i:n for i,n in choices.items()
                       if i == int(b["confirmed_source_id"])}
        mid = next(iter(choices)) if len(choices) == 1 else None
        print(f'{b["name"]:18} -> ' +
              (f'id={mid}' if mid is not None else f'UNRESOLVED: {choices}'),
              flush=True)
        resolved.append((b["name"],mid))
    ids = [mid for _,mid in resolved if mid is not None]
    if len(ids) != len(set(ids)) or any(mid is None for _,mid in resolved):
        raise RuntimeError("Ambiguous or missing manufacturer IDs; no data imported")
    print("Index validated: " + index, flush=True)
    return index, resolved


def physical_size_mib(target):
    # Physical InnoDB .ibd files; excludes redo logs and other volume overhead.
    with target.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(SUM(FILE_SIZE),0) AS physical_bytes
               FROM information_schema.INNODB_TABLESPACES
               WHERE NAME LIKE %s""",
            (os.environ["DEST_DATABASE"] + "/%",))
        size = int(cur.fetchone()["physical_bytes"])
    if size <= 0:
        raise RuntimeError("Physical InnoDB file sizes unavailable; stopped safely")
    return size / (1024*1024)


def disk_guard(target, limit):
    used = physical_size_mib(target)
    if used >= limit:
        raise RuntimeError(f"InnoDB files ≈{used:.0f} MiB reached {limit} MiB guard")
    return used


def ensure_target(target):
    with target.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db")
        if cur.fetchone()["db"] != os.environ["DEST_DATABASE"]:
            raise RuntimeError("Unexpected destination database")
        for table in ("catalogue_oem","catalogue_oem_brand_progress"):
            cur.execute("SHOW TABLES LIKE %s",(table,))
            if cur.fetchone() is None:
                raise RuntimeError("Missing staging table: " + table)


def brand_start(target, brand, manufacturer_id):
    with target.cursor() as cur:
        cur.execute("SELECT manufacturer_id,status FROM catalogue_oem_brand_progress WHERE brand=%s",(brand,))
        previous = cur.fetchone()
        if previous and int(previous["manufacturer_id"]) != manufacturer_id:
            raise RuntimeError("Source ID changed for " + brand)
        if previous and previous["status"] == "complete":
            print("SKIP already complete: " + brand,flush=True)
            return False
        cur.execute(
            """INSERT INTO catalogue_oem_brand_progress
               (brand,manufacturer_id,status,scanned_in_attempt)
               VALUES (%s,%s,'running',0)
               ON DUPLICATE KEY UPDATE
                 status='running',scanned_in_attempt=0,
                 started_at=CURRENT_TIMESTAMP,completed_at=NULL""",
            (brand,manufacturer_id))
    target.commit()
    return True


def brand_batch(target, brand, batch):
    # Each row is a compact 4-element list read from the temporary local spool.
    records = [tuple(row) for row in batch]
    try:
        with target.cursor() as cur:
            cur.executemany(
                """INSERT INTO catalogue_oem
                   (supplier_id,article_number,oem_manufacturer_id,oem_number)
                   VALUES (%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE oem_number=oem_number""",records)
            added = max(0,cur.rowcount)
            cur.execute(
                """UPDATE catalogue_oem_brand_progress SET
                   scanned_in_attempt=scanned_in_attempt+%s,
                   inserted_unique=inserted_unique+%s WHERE brand=%s""",
                (len(batch),added,brand))
        target.commit()
        return added
    except BaseException:
        target.rollback()
        raise


def import_brand(source,target,brand,mid,index,batch_size,limit_rows,disk_limit,
                 max_spool_mib):
    if not brand_start(target,brand,mid):
        return
    print(f"IMPORT {brand} ({mid})",flush=True)
    scanned = added = batches = 0
    began = monotonic()
    sql = ("SELECT supplierId,DataSupplierArticleNumber,manufacturerId,OENbr "
           f"FROM article_oe FORCE INDEX ({index}) WHERE manufacturerId=%s")
    params = [mid]
    if limit_rows:
        sql += " LIMIT %s"
        params.append(limit_rows)

    # IMPORTANT: The old version kept a source SELECT open while doing slow
    # remote writes. MySQL cancelled that long-running SELECT with error 3024.
    # Drain the indexed read quickly to a bounded LOCAL temporary file first.
    # This keeps RAM bounded and closes the source SELECT before any batch
    # goes over the Railway SSH tunnel.
    source_rows = 0
    spool_started = monotonic()
    with tempfile.TemporaryFile(mode="w+t",encoding="utf-8",newline="") as spool:
        with source.cursor(pymysql.cursors.SSDictCursor) as cur:
            cur.execute(sql,params)
            while True:
                chunk = cur.fetchmany(2000)
                if not chunk:
                    break
                for row in chunk:
                    compact = [row["supplierId"],row["DataSupplierArticleNumber"],
                               row["manufacturerId"],row["OENbr"]]
                    spool.write(json.dumps(compact,ensure_ascii=False,
                                           separators=(",",":"))+"\\n")
                source_rows += len(chunk)
                if spool.tell() > max_spool_mib * 1024 * 1024:
                    raise RuntimeError(
                        f"Local OEM spool exceeded {max_spool_mib} MiB. "
                        "No new destination rows were written in this attempt."
                    )
                if source_rows % 100000 == 0:
                    print(f"{brand}: read {source_rows:,} source rows to "
                          "temporary file",flush=True)
        print(f"{brand}: source query finished; {source_rows:,} rows buffered "
              f"locally in {monotonic()-spool_started:.1f}s. "
              "Starting Railway write batches.",flush=True)
        spool.seek(0)
        while True:
            rows = [json.loads(line) for line in islice(spool,batch_size)]
            if not rows:
                break
            if batches % 10 == 0:
                mib = disk_guard(target,disk_limit)
            added += brand_batch(target,brand,rows)
            scanned += len(rows)
            batches += 1
            if batches % 10 == 0:
                elapsed = max(.1,monotonic()-began)
                print(f"{brand}: scanned={scanned:,}; new OEM={added:,}; "
                      f"{scanned/elapsed:.0f} rows/s; InnoDB files≈{mib:.0f} MiB",
                      flush=True)

    if scanned != source_rows:
        raise RuntimeError(
            f"{brand}: local spool mismatch: read {source_rows}, wrote {scanned}"
        )
    if limit_rows:
        print(f"PARTIAL TEST {brand}: {scanned:,} scanned; "
              "next run will reread the brand, skipping duplicates.",flush=True)
    else:
        with target.cursor() as cur:
            cur.execute(
                """UPDATE catalogue_oem_brand_progress
                   SET status='complete',completed_at=CURRENT_TIMESTAMP
                   WHERE brand=%s""",(brand,))
        target.commit()
        print(f"COMPLETE {brand}: scanned={scanned:,}; new OEM={added:,}",flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--brand",default="all",help="Exact manufacturer from manifest, or all")
    p.add_argument("--first",type=int,choices=(10,30),default=30,
                   help="When --brand all: only the first 10 or all 30 makes (Volvo first)")
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--batch-size",type=int,default=500)
    p.add_argument("--max-rows",type=int,default=0,
                   help="Test only: 0 means all rows for the brand")
    p.add_argument("--max-db-mib",type=int,default=2000)
    p.add_argument("--max-spool-mib",type=int,default=768,
                   help="Max temporary local disk space for source read per brand")
    p.add_argument("--confirm-staging",action="store_true")
    a = p.parse_args()
    if not a.confirm_staging:
        p.error("Must specify --confirm-staging")
    if not 50 <= a.batch_size <= 1000 or a.max_rows < 0:
        p.error("batch-size 50..1000, max-rows >= 0")
    if not 500 <= a.max_db_mib <= 3500:
        p.error("max-db-mib 500..3500")
    if not 64 <= a.max_spool_mib <= 4096:
        p.error("max-spool-mib must be 64..4096")
    if os.getenv("DEST_DATABASE") not in ("railway","catalogue"):
        p.error("Unexpected destination database")
    if os.getenv("DEST_HOST") not in ("127.0.0.1","localhost"):
        p.error("Use Railway tunnel on localhost")
    if os.getenv("DEST_PORT") == os.getenv("SOURCE_PORT","3306"):
        p.error("Source and destination ports must be different")
    makes = json.loads(MANIFEST.read_text(encoding="utf-8"))["brands"]
    if len(makes)!=30 or makes[0]["name"]!="Volvo":
        p.error("Manifest must contain Volvo first and 30 brands")
    if a.brand == "all":
        selected = makes[:a.first]
    else:
        selected = [m for m in makes if m["name"] == a.brand]
    if not selected:
        p.error("Brand not in manifest")
    print("Selected makes ("+str(len(selected))+"): "+", ".join(m["name"] for m in selected),flush=True)
    source = db("SOURCE","td1q2018",source=True)
    try:
        index,mapped = resolve(source,selected)
        if a.preflight:
            print("PREFLIGHT OK — no data changed",flush=True)
            return
        target = db("DEST",os.environ["DEST_DATABASE"])
        try:
            ensure_target(target)
            disk_guard(target,a.max_db_mib)
            with target.cursor() as cur:
                cur.execute("SELECT GET_LOCK(%s,0) AS acquired",(LOCK,))
                if cur.fetchone()["acquired"]!=1:
                    raise RuntimeError("A priority OEM importer is already running")
            try:
                for brand,mid in mapped:
                    import_brand(source,target,brand,mid,index,a.batch_size,
                                 a.max_rows,a.max_db_mib,a.max_spool_mib)
            finally:
                with target.cursor() as cur:
                    cur.execute("DO RELEASE_LOCK(%s)",(LOCK,))
            print("FINISHED selected OEM brands",flush=True)
        finally:
            target.close()
    finally:
        source.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped. Committed batches remain; interrupted brand can be retried.",flush=True)
        sys.exit(130)
    except Exception as e:
        print(f"STOPPED: {e}",file=sys.stderr,flush=True)
        sys.exit(1)
