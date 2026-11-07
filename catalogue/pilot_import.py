"""Bounded, repeatable Volvo OEM pilot import via an existing Railway TCP tunnel.

Reads source td1q2018; writes ONLY to explicitly configured staging MySQL.
No destructive SQL. Uses batch writes to reduce tunnel round-trips.
"""
import os
import time
import pymysql

MAX_ROWS = int(os.environ.get("PILOT_MAX_ROWS", "1000"))
BATCH_SIZE = 100
if not 1 <= MAX_ROWS <= 5000:
    raise SystemExit("PILOT_MAX_ROWS must be in 1..5000")
if os.environ.get("DEST_DATABASE") not in ("railway", "catalogue"):
    raise SystemExit("Refusing an unexpected destination database")
if os.environ.get("SOURCE_PORT", "3306") == os.environ.get("DEST_PORT", ""):
    raise SystemExit("Source and destination ports must be different")

def connect(prefix, database):
    return pymysql.connect(
        host=os.environ.get(prefix + "_HOST", "127.0.0.1"),
        port=int(os.environ.get(prefix + "_PORT", "3306")),
        user=os.environ[prefix + "_USER"],
        password=os.environ.get(prefix + "_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        connect_timeout=8,
        read_timeout=30 if prefix == "DEST" else 120,
        write_timeout=30,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

print("1/4 Connecting to local source and Railway staging...", flush=True)
source = connect("SOURCE", "td1q2018")
try:
    target = connect("DEST", os.environ["DEST_DATABASE"])
    try:
        with target.cursor() as cur:
            cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
            info = cur.fetchone()
            print(f"2/4 Destination reachable: database={info['db']}, version={info['version']}", flush=True)
            for name in ("catalogue_parts", "catalogue_oem"):
                cur.execute("SHOW TABLES LIKE %s", (name,))
                if cur.fetchone() is None:
                    raise RuntimeError(f"Destination staging table {name} is missing")
        with source.cursor() as cur:
            print(f"3/4 Reading up to {MAX_ROWS} Volvo OEM references...", flush=True)
            cur.execute(
                """SELECT oe.supplierId AS supplier_id,
                          oe.DataSupplierArticleNumber AS article_number,
                          oe.manufacturerId AS oem_manufacturer_id,
                          oe.OENbr AS oem_number,
                          a.NormalizedDescription AS name_source
                   FROM article_oe oe
                   JOIN articles a
                     ON a.supplierId = oe.supplierId
                    AND a.DataSupplierArticleNumber = oe.DataSupplierArticleNumber
                   WHERE oe.manufacturerId = 120
                   LIMIT %s""",
                (MAX_ROWS,),
            )
            rows = cur.fetchall()
        print(f"4/4 Transferring {len(rows)} records in batches of {BATCH_SIZE}...", flush=True)
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start+BATCH_SIZE]
            unique_parts = {
                (r["supplier_id"], r["article_number"]): r["name_source"] for r in batch
            }
            parts = [(k[0], k[1], v) for k, v in unique_parts.items()]
            oems = [
                (r["supplier_id"], r["article_number"], r["oem_manufacturer_id"], r["oem_number"])
                for r in batch
            ]
            begun = time.monotonic()
            try:
                with target.cursor() as cur:
                    cur.executemany(
                        """INSERT INTO catalogue_parts
                           (supplier_id, article_number, name_source)
                           VALUES (%s,%s,%s)
                           ON DUPLICATE KEY UPDATE name_source=VALUES(name_source)""",
                        parts,
                    )
                    cur.executemany(
                        """INSERT IGNORE INTO catalogue_oem
                           (supplier_id, article_number, oem_manufacturer_id, oem_number)
                           VALUES (%s,%s,%s,%s)""",
                        oems,
                    )
                target.commit()
            except Exception:
                target.rollback()
                raise
            print(f"  Committed {start + len(batch)}/{len(rows)} "
                  f"({time.monotonic()-begun:.1f}s)", flush=True)
        print(f"SUCCESS: processed {len(rows)} Volvo OEM references", flush=True)
    finally:
        target.close()
finally:
    source.close()
