"""Read-only Volvo-focused verification on local MySQL td1q2018.

Reads only indexed, bounded samples for 3 Volvo families. Writes a JSON
report next to this script. No Railway calls or changes to source tables.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pymysql

SOURCE = "td1q2018"
REPORT = Path(__file__).with_name("volvo_deep_audit.json")
VOLVO_ID = 120
TARGETS = {
    "XC90 II": ("XC90", 13084),
    "XC60 II": ("XC60", 37773),
    "XC40": ("XC40", None),
}


def main():
    if os.getenv("SOURCE_HOST", "127.0.0.1") not in ("127.0.0.1", "localhost"):
        raise SystemExit("Only the local MySQL source is permitted")
    db = pymysql.connect(
        host=os.getenv("SOURCE_HOST", "127.0.0.1"),
        port=int(os.getenv("SOURCE_PORT", "3306")),
        user=os.getenv("SOURCE_USER", "root"),
        password=os.getenv("SOURCE_PASSWORD", ""),
        database=SOURCE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
        read_timeout=30,
    )
    report = {
        "source": SOURCE,
        "mode": "READ-ONLY bounded sample, no source/target changes",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "warnings": [
            "Samples and estimates are not proof of completeness or fitment.",
            "PictureName is a filename, not proof the image file or license exists.",
            "TecDoc vehicle identifiers are not automatically plan.parts K-Types.",
        ],
        "results": {},
    }

    def query(name, sql, args=()):
        t = time.monotonic()
        try:
            with db.cursor() as cur:
                cur.execute(sql, args)
                rows = cur.fetchall()
            report["results"][name] = {
                "ok": True, "duration_seconds": round(time.monotonic() - t, 3),
                "rows": rows,
            }
            print("OK   ", name, f"({len(rows)} rows)", flush=True)
            return rows
        except pymysql.MySQLError as exc:
            msg = str(exc)[:300]
            report["results"][name] = {"ok": False, "error": msg}
            print("FAIL ", name, msg, flush=True)
            return []

    try:
        with db.cursor() as cur:
            cur.execute("SELECT DATABASE() AS source_name")
            if cur.fetchone()["source_name"] != SOURCE:
                raise RuntimeError("Unexpected MySQL database")
            cur.execute("SET SESSION max_execution_time=10000")
            cur.execute("SET SESSION TRANSACTION READ ONLY")

        models = query(
            "volvo_passenger_models",
            """SELECT id,description,fulldescription,constructioninterval
               FROM models WHERE manufacturerid=%s AND ispassengercar='True'
               ORDER BY id LIMIT 500""",
            (VOLVO_ID,),
        )
        chosen = []
        for title, (needle, preferred_id) in TARGETS.items():
            selected = next((m for m in models if m["id"] == preferred_id), None)
            if selected is None:
                matches = [
                    m for m in models
                    if needle.casefold() in str(m["description"]).casefold()
                ]
                if title.endswith(" II"):
                    second = [
                        m for m in matches
                        if " II" in str(m["description"])
                    ]
                    selected = (second or matches or [None])[0]
                else:
                    selected = (matches or [None])[0]
            if selected is None:
                report["results"]["selected_" + title] = {
                    "ok": False, "error": "Target model not present in returned models"
                }
                continue
            chosen.append((title, selected))
            model_id = selected["id"]
            query(
                "modifications_" + title,
                """SELECT id,modelid,description,fulldescription,constructioninterval,
                          haslink,ispassengercar
                   FROM passanger_cars
                   WHERE modelid=%s ORDER BY id LIMIT 8""",
                (model_id,),
            )
            query(
                "modification_count_" + title,
                "SELECT COUNT(*) AS count FROM passanger_cars WHERE modelid=%s",
                (model_id,),
            )

        # Test the indexed path for one concrete variant of each target model.
        for title, model in chosen:
            rows = report["results"].get("modifications_" + title, {}).get("rows", [])
            if not rows:
                continue
            car_id = rows[0]["id"]
            key = title.replace(" ", "_")
            for name, table in [
                ("attributes", "passanger_car_attributes"),
                ("part_tree", "passanger_car_trees"),
                ("part_groups", "passanger_car_pds"),
                ("quick_start", "passanger_car_qsi"),
            ]:
                field = "passangercarid"
                query(
                    key + "_" + name + "_count",
                    "SELECT COUNT(*) AS count FROM " + table + " WHERE " + field + "=%s",
                    (car_id,),
                )
                query(
                    key + "_" + name + "_sample",
                    "SELECT * FROM " + table + " WHERE " + field + "=%s LIMIT 12",
                    (car_id,),
                )
            # Index on article_links.linkageid; do not infer linkage type yet.
            links = query(
                key + "_article_links",
                """SELECT supplierid,productid,linkagetypeid,linkageid,
                          datasupplierarticlenumber
                   FROM article_links FORCE INDEX (linkageid)
                   WHERE linkageid=%s LIMIT 15""",
                (car_id,),
            )
            for item in links[:3]:
                supplier_id = item["supplierid"]
                art = item["datasupplierarticlenumber"]
                query(
                    key + "_linked_article_" + str(supplier_id) + "_" + str(art)[:30],
                    """SELECT supplierId,DataSupplierArticleNumber,Description,
                              NormalizedDescription,HasPassengerCar
                       FROM articles WHERE supplierId=%s
                         AND DataSupplierArticleNumber=%s LIMIT 1""",
                    (supplier_id, art),
                )
                query(
                    key + "_linked_photo_" + str(supplier_id) + "_" + str(art)[:30],
                    """SELECT supplierId,DataSupplierArticleNumber,
                              DocumentType,PictureName,DocumentName
                       FROM article_images WHERE supplierId=%s
                         AND DataSupplierArticleNumber=%s LIMIT 3""",
                    (supplier_id, art),
                )
        query(
            "volvo_article_cross_sample",
            """SELECT manufacturerId,OENbr,SupplierId,PartsDataSupplierArticleNumber
               FROM article_cross FORCE INDEX (manufacturerId)
               WHERE manufacturerId=%s LIMIT 15""",
            (VOLVO_ID,),
        )
        oem_sample = query(
            "volvo_oem_article_sample",
            """SELECT supplierid,datasupplierarticlenumber,OENbr,IsAdditive
               FROM article_oe FORCE INDEX (manufacturerId)
               WHERE manufacturerId=%s LIMIT 350""",
            (VOLVO_ID,),
        )
        seen = set()
        selected_articles = []
        for r in oem_sample:
            identity = (r["supplierid"], r["datasupplierarticlenumber"])
            if identity not in seen:
                seen.add(identity)
                selected_articles.append(identity)
            if len(selected_articles) >= 15:
                break
        for index, (supplier_id, article) in enumerate(selected_articles):
            query(
                "oem_article_" + str(index),
                """SELECT supplierId,DataSupplierArticleNumber,
                          Description,NormalizedDescription
                   FROM articles WHERE supplierId=%s
                   AND DataSupplierArticleNumber=%s LIMIT 1""",
                (supplier_id, article),
            )
            query(
                "oem_photo_" + str(index),
                """SELECT supplierId,DataSupplierArticleNumber,
                          DocumentType,PictureName,DocumentName
                   FROM article_images WHERE supplierId=%s
                   AND DataSupplierArticleNumber=%s LIMIT 3""",
                (supplier_id, article),
            )
        query(
            "suppliers_sample",
            """SELECT id,description,matchcode
               FROM suppliers WHERE id IN (1,2,3,4,5,6,7,8,9,10)
               ORDER BY id LIMIT 10""",
        )
        query(
            "product_taxonomy",
            """SELECT id,description,normalizeddescription,assemblygroupdescription
               FROM prd ORDER BY id LIMIT 15""",
        )
        report["selected_models"] = {
            title: {"id": model["id"], "description": model["description"]}
            for title, model in chosen
        }
    finally:
        db.close()
        REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print("\nREPORT:", REPORT, flush=True)
        print("Source database unchanged. Upload the JSON report for next analysis.", flush=True)


if __name__ == "__main__":
    main()
