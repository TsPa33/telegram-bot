"""Read-only discovery of Volvo data in local td1q2018.

Writes only a local JSON report. Does not alter the source database or Railway.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pymysql

DB_NAME = "td1q2018"
VOLVO_MFR_ID = 120
REPORT = Path(__file__).with_name("volvo_source_audit.json")
FOCUS = (
    "manufacturers", "models", "passenger_cars", "passenger_car_pds",
    "articles", "article_oe", "article_cross", "article_attributes",
    "article_images", "article_links", "article_li", "article_numbers",
)
NAME_RE = re.compile(
    r"(supplier|image|picture|photo|model|manufactur|passenger|vehicle|"
    r"article|generic|category|tree|assembly|group|criteria|text|link|media)",
    re.IGNORECASE,
)

def simplify(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"binary": True, "size": len(value)}
    value = str(value)
    return value[:180] + ("…" if len(value)>180 else "")

def safe_sample(con, table, columns):
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        return {"error": "Unsupported table name"}
    names = [
        c["column"] for c in columns
        if c["data_type"].lower() not in (
            "blob","tinyblob","mediumblob","longblob",
            "binary","varbinary","geometry","point","polygon",
        )
        and re.fullmatch(r"[A-Za-z0-9_]+", c["column"])
    ][:16]
    if not names:
        return {"note": "No safe scalar columns to sample"}
    quote = chr(96)
    cols = ", ".join(quote+n+quote for n in names)
    by_name = {c["column"].casefold():c["column"] for c in columns}
    where = ""
    params = ()
    if table == "models" and "manufacturerid" in by_name:
        where = " WHERE " + quote + by_name["manufacturerid"] + quote + "=%s"
        params = (VOLVO_MFR_ID,)
    elif table == "article_oe" and "manufacturerid" in by_name:
        where = " WHERE " + quote + by_name["manufacturerid"] + quote + "=%s"
        params = (VOLVO_MFR_ID,)
    elif table == "manufacturers":
        where = " WHERE id=%s"
        params = (VOLVO_MFR_ID,)
    with con.cursor() as cur:
        cur.execute("SELECT "+cols+" FROM "+quote+table+quote+where+" LIMIT 3",params)
        return {"volvo_filtered":bool(where),"rows":[
            {k:simplify(v) for k,v in row.items()} for row in cur.fetchall()
        ]}

def main():
    if os.getenv("SOURCE_HOST","127.0.0.1") not in ("127.0.0.1","localhost"):
        raise SystemExit("Only local source is supported")
    con = pymysql.connect(
        host=os.getenv("SOURCE_HOST","127.0.0.1"),
        port=int(os.getenv("SOURCE_PORT","3306")),
        user=os.getenv("SOURCE_USER","root"),
        password=os.getenv("SOURCE_PASSWORD",""),
        database=DB_NAME,charset="utf8mb4",autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,read_timeout=30,
    )
    try:
        with con.cursor() as cur:
            cur.execute("SELECT DATABASE() AS name")
            if cur.fetchone()["name"]!=DB_NAME:
                raise SystemExit("Incorrect source database")
            cur.execute("SET SESSION max_execution_time=8000")
            cur.execute(
                """SELECT TABLE_NAME AS table_name,TABLE_ROWS AS estimated_rows,
                          DATA_LENGTH AS data_bytes,INDEX_LENGTH AS index_bytes
                   FROM information_schema.TABLES
                   WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'""",(DB_NAME,)
            )
            table_rows=cur.fetchall()
            cur.execute(
                """SELECT TABLE_NAME AS table_name,COLUMN_NAME AS column_name,
                          DATA_TYPE AS data_type,COLUMN_TYPE AS column_type,
                          COLUMN_KEY AS column_key
                   FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME,ORDINAL_POSITION""",
                (DB_NAME,)
            )
            column_rows=cur.fetchall()
            cur.execute(
                """SELECT TABLE_NAME AS table_name,INDEX_NAME AS index_name,
                          SEQ_IN_INDEX AS seq_no,COLUMN_NAME AS column_name
                   FROM information_schema.STATISTICS
                   WHERE TABLE_SCHEMA=%s
                   ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX""",(DB_NAME,)
            )
            index_rows=cur.fetchall()
        fields={}
        for c in column_rows:
            fields.setdefault(c["table_name"],[]).append({
                "column":c["column_name"],"data_type":c["data_type"],
                "sql_type":c["column_type"],"key":c["column_key"]
            })
        indexes={}
        for i in index_rows:
            indexes.setdefault(i["table_name"],{}).setdefault(
                i["index_name"],[]
            ).append(i["column_name"])
        tables={}
        for row in table_rows:
            name=row["table_name"]
            tables[name]={
                "estimated_rows":int(row["estimated_rows"] or 0),
                "estimated_data_mib":round(int(row["data_bytes"] or 0)/1048576,2),
                "estimated_index_mib":round(int(row["index_bytes"] or 0)/1048576,2),
                "columns":fields.get(name,[]),
                "indexes":indexes.get(name,{})
            }
        candidates=sorted(name for name in tables if name in FOCUS or NAME_RE.search(name))
        samples={}
        for name in candidates:
            try:
                samples[name]=safe_sample(con,name,fields.get(name,[]))
                status="OK"
            except (pymysql.MySQLError,ValueError,TypeError) as exc:
                status="FAILED"
                samples[name]={"error":str(exc)[:250]}
            print(f"{status:6} {name}",flush=True)
        result={
            "source":DB_NAME,"scope":"READ ONLY, at most 3 sample rows per table",
            "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "volvo_manufacturer_id":VOLVO_MFR_ID,
            "table_count":len(tables),"candidate_count":len(candidates),
            "candidates":candidates,"metadata":tables,"samples":samples,
        }
        REPORT.write_text(
            json.dumps(result,ensure_ascii=False,indent=2,default=str),
            encoding="utf-8"
        )
        print("AUDIT READY:",REPORT,flush=True)
        print("Source unchanged; no Railway writes. Inspect report before sharing.",flush=True)
    finally:
        con.close()

if __name__=="__main__":
    main()
