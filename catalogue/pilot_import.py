"""One-time bounded local-to-staging pilot import. Never writes to the source DB.

Run on the Windows PC hosting td1q2018, with a Railway TCP tunnel open.
Environment variables:
  SOURCE_HOST, SOURCE_PORT, SOURCE_USER, SOURCE_PASSWORD
  DEST_HOST, DEST_PORT, DEST_USER, DEST_PASSWORD, DEST_DATABASE
Use a staging destination account only.
"""
import os
import sys
import pymysql

MAX_ROWS = int(os.environ.get("PILOT_MAX_ROWS", "1000"))
if not 1 <= MAX_ROWS <= 5000:
    raise SystemExit("PILOT_MAX_ROWS must be 1..5000")
if os.environ.get("DEST_DATABASE") not in ("railway", "catalogue"):
    raise SystemExit("Destination database must be railway or catalogue in isolated staging")

def connect(prefix, database):
    return pymysql.connect(
        host=os.environ.get(prefix + "_HOST", "127.0.0.1"),
        port=int(os.environ.get(prefix + "_PORT", "3306")),
        user=os.environ[prefix + "_USER"],
        password=os.environ.get(prefix + "_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=120,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )

source = connect("SOURCE", "td1q2018")
target = connect("DEST", os.environ["DEST_DATABASE"])
try:
    with source.cursor() as cur:
        # Volvo OEM references only: a small, reproducible integration test.
        cur.execute(
            """SELECT oe.supplierId AS supplier_id,
                      oe.DataSupplierArticleNumber AS article_number,
                      oe.manufacturerId AS oem_manufacturer_id,
                      oe.OENbr AS oem_number,
                      a.NormalizedDescription AS name_source
               FROM article_oe oe
               INNER JOIN articles a
                 ON a.supplierId=oe.supplierId
                AND a.DataSupplierArticleNumber=oe.DataSupplierArticleNumber
               WHERE oe.manufacturerId=120
               LIMIT %s""", (MAX_ROWS,))
        rows = cur.fetchall()
    with target.cursor() as cur:
        for row in rows:
            cur.execute(
                """INSERT INTO catalogue_parts
                   (supplier_id, article_number, name_source)
                   VALUES (%s,%s,%s)
                   ON DUPLICATE KEY UPDATE name_source=VALUES(name_source)""",
                (row["supplier_id"], row["article_number"], row["name_source"]),
            )
            cur.execute(
                """INSERT IGNORE INTO catalogue_oem
                   (supplier_id, article_number, oem_manufacturer_id, oem_number)
                   VALUES (%s,%s,%s,%s)""",
                (row["supplier_id"], row["article_number"],
                 row["oem_manufacturer_id"], row["oem_number"]),
            )
    target.commit()
    print(f"Pilot imported {len(rows)} Volvo OEM references to catalogue-staging")
except Exception:
    target.rollback()
    raise
finally:
    source.close()
    target.close()
