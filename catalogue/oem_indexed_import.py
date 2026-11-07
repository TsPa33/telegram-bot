"""OEM importer using the EXISTING (supplierId, DataSupplierArticleNumber) index.

Iterates source ARTICLES by PK, then reads OEMs per article with an indexed
equality probe. Progress is checkpointed in Railway atomically with inserted
OEM rows. No schema/index changes to the 50-GiB source.
"""
import argparse
import os
import time
from collections import defaultdict

import pymysql

JOB = "oem-by-article"
def conn(prefix, database, autocommit):
    return pymysql.connect(
        host=os.environ.get(prefix + "_HOST", "127.0.0.1"),
        port=int(os.environ.get(prefix + "_PORT", "3306")),
        user=os.environ[prefix + "_USER"],
        password=os.environ.get(prefix + "_PASSWORD", ""),
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=120 if prefix == "SOURCE" else 60,
        write_timeout=60,
        autocommit=autocommit,
    )

def index_prefixes(connection, name):
    with connection.cursor() as cur:
        cur.execute("SHOW INDEX FROM `" + name + "`")
        indexes = defaultdict(list)
        for row in cur.fetchall():
            indexes[row["Key_name"]].append(
                (int(row["Seq_in_index"]),row["Column_name"].casefold())
            )
    return {k: tuple(v for _,v in sorted(items)) for k,items in indexes.items()}

def verify_source(source):
    a = index_prefixes(source,"articles")
    o = index_prefixes(source,"article_oe")
    prefix = ("supplierid", "datasupplierarticlenumber")
    for table, found in (("articles",a),("article_oe",o)):
        if not any(keys[:2] == prefix for keys in found.values()):
            print(f"No suitable {table} index. Found {found}",flush=True)
            raise SystemExit("Stopped safely. Source unchanged.")
    print("INDEX OK: both articles and article_oe support indexed article-key lookups",flush=True)

def check_target(dest):
    with dest.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db")
        if cur.fetchone()["db"] != os.environ["DEST_DATABASE"]:
            raise RuntimeError("Unexpected destination database")
        for name in ("catalogue_oem","catalogue_import_progress"):
            cur.execute("SHOW TABLES LIKE %s",(name,))
            if cur.fetchone() is None:
                raise RuntimeError("Missing Railway staging table " + name)

def progress(dest):
    with dest.cursor() as cur:
        cur.execute(
            """SELECT last_supplier_id,last_article_number,processed
               FROM catalogue_import_progress WHERE job=%s""",
            (JOB,),
        )
        return cur.fetchone()

def next_articles(source, marker, limit):
    with source.cursor() as cur:
        cur.execute(
            """SELECT supplierId, DataSupplierArticleNumber
               FROM articles
               WHERE (supplierId, DataSupplierArticleNumber) > (%s,%s)
               ORDER BY supplierId, DataSupplierArticleNumber LIMIT %s""",
            (*marker,limit),
        )
        return cur.fetchall()

def get_oems(source, article):
    with source.cursor() as cur:
        cur.execute(
            """SELECT supplierId, DataSupplierArticleNumber, manufacturerId, OENbr
               FROM article_oe
               WHERE supplierId=%s AND DataSupplierArticleNumber=%s""",
            (article["supplierId"],article["DataSupplierArticleNumber"]),
        )
        return cur.fetchall()

def size_guard(dest,max_mib):
    with dest.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(SUM(data_length+index_length),0)/1024/1024 AS mib
               FROM information_schema.tables WHERE table_schema=DATABASE()"""
        )
        mib = float(cur.fetchone()["mib"])
        if mib >= max_mib:
            raise RuntimeError(f"Estimated staging DB size {mib:.1f} MiB exceeded guard {max_mib}")
        return mib

def run():
    p=argparse.ArgumentParser()
    p.add_argument("--preflight",action="store_true")
    p.add_argument("--confirm-staging",action="store_true")
    p.add_argument("--max-articles",type=int,default=250)
    p.add_argument("--batch-articles",type=int,default=25)
    p.add_argument("--max-db-mib",type=int,default=3000)
    args=p.parse_args()
    if not args.confirm_staging:
        p.error("--confirm-staging is mandatory")
    if not 1 <= args.batch_articles <= 100 or not 1 <= args.max_articles <= 20000:
        p.error("batch-articles must be 1..100, max-articles 1..20000")
    if not 100 <= args.max_db_mib <= 3500:
        p.error("max-db-mib must be 100..3500")
    if os.getenv("DEST_DATABASE") not in ("railway","catalogue"):
        p.error("Unexpected database; target must be isolated staging")
    if os.getenv("DEST_HOST") not in ("127.0.0.1","localhost"):
        p.error("Destination must be local Railway tunnel")
    if os.getenv("DEST_PORT")==os.getenv("SOURCE_PORT","3306"):
        p.error("Tunnel port must differ from local MySQL port")

    source=conn("SOURCE","td1q2018",True)
    try:
        verify_source(source)
        if args.preflight:
            print("PREFLIGHT OK — source not modified, no data written",flush=True)
            return
        dest=conn("DEST",os.environ["DEST_DATABASE"],False)
        try:
            check_target(dest)
            state=progress(dest)
            marker=(int(state["last_supplier_id"]),state["last_article_number"]) if state else (0,"")
            prior=int(state["processed"]) if state else 0
            moved=0
            oem_rows=0
            print(f"Starting {JOB} after article key {marker}, earlier article groups={prior}",flush=True)
            while moved < args.max_articles:
                used=size_guard(dest,args.max_db_mib)
                start=time.monotonic()
                batch=next_articles(source,marker,min(args.batch_articles,args.max_articles-moved))
                if not batch:
                    print("SOURCE EXHAUSTED — OEM article-key scan finished",flush=True)
                    break
                oems=[]
                for article in batch:
                    oems.extend(get_oems(source,article))
                end=batch[-1]
                next_marker=(int(end["supplierId"]),str(end["DataSupplierArticleNumber"]))
                try:
                    with dest.cursor() as cur:
                        if oems:
                            # Keep packets modest, even for articles with many OEM numbers.
                            data=[(r["supplierId"],r["DataSupplierArticleNumber"],
                                   r["manufacturerId"],r["OENbr"]) for r in oems]
                            for i in range(0,len(data),500):
                                cur.executemany(
                                    """INSERT IGNORE INTO catalogue_oem
                                      (supplier_id,article_number,oem_manufacturer_id,oem_number)
                                      VALUES (%s,%s,%s,%s)""",data[i:i+500])
                        cur.execute(
                            """INSERT INTO catalogue_import_progress
                               (job,last_supplier_id,last_article_number,processed)
                               VALUES (%s,%s,%s,%s)
                               ON DUPLICATE KEY UPDATE
                               last_supplier_id=VALUES(last_supplier_id),
                               last_article_number=VALUES(last_article_number),
                               processed=VALUES(processed)""",
                            (JOB,*next_marker,prior+len(batch)),
                        )
                    dest.commit()
                except BaseException:
                    dest.rollback()
                    raise
                moved+=len(batch)
                oem_rows+=len(oems)
                prior+=len(batch)
                marker=next_marker
                print(f"COMMITTED {moved}/{args.max_articles} article groups, "
                      f"{oem_rows} OEM source rows this run, DB≈{used:.1f} MiB, "
                      f"article key={marker}, batch={time.monotonic()-start:.1f}s",flush=True)
            print(f"SUCCESS: {moved} article groups scanned, {oem_rows} OEM rows processed",flush=True)
        finally:
            dest.close()
    finally:
        source.close()

if __name__=="__main__":
    run()
