"""Read-only metadata inventory for VIN/vehicle characteristics in local td1q2018.

No full data scans, row samples, credentials, VIN values or destination connections.
Run on the Windows host that has access to the local MySQL.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pymysql

DATABASE = "td1q2018"
# Vehicle-related *schema* terms: deliberately broad for multilingual catalogues.
VIN_TERMS = re.compile(r"vin|chassis|chassi|frame.?no|vehicle.?ident|fahrgestell|wmi|vds|vis", re.I)
TECH_TERMS = re.compile(
    r"passang|passeng|commercial|truck|vehicle|car_|engine|motor|"
    r"gear|transmission|fuel|body|construction|production|year|"
    r"drive|capacity|displacement|ktyp|ktype|typeid|type_id|"
    r"manufacturer|model|attrib|criteria|vin",
    re.I,
)
IMPORTANT_TABLES = {
    "manufacturers", "models", "passanger_cars", "passenger_cars",
    "passanger_car_attributes", "passenger_car_attributes",
    "passanger_car_qsi", "passanger_car_trees", "article_links",
}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def matches(table: str, column: str) -> tuple[bool, bool]:
    return bool(VIN_TERMS.search(table) or VIN_TERMS.search(column)), bool(
        TECH_TERMS.search(table) or TECH_TERMS.search(column)
    )


def inventory(connection) -> dict:
    with connection.cursor() as cur:
        cur.execute("SELECT DATABASE() AS db, VERSION() AS version")
        identity = cur.fetchone()
        if identity["db"] != DATABASE:
            raise RuntimeError("Wrong MySQL database; refusing to inspect")
        cur.execute(
            """SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
                      DATA_TYPE AS data_type, COLUMN_TYPE AS column_type,
                      COLUMN_KEY AS column_key, IS_NULLABLE AS is_nullable
                 FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME, ORDINAL_POSITION""",
            (DATABASE,),
        )
        cols = cur.fetchall()
        cur.execute(
            """SELECT TABLE_NAME AS table_name, TABLE_ROWS AS estimated_rows
                 FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'
                ORDER BY TABLE_NAME""",
            (DATABASE,),
        )
        table_rows = cur.fetchall()
        cur.execute(
            """SELECT TABLE_NAME AS table_name, INDEX_NAME AS index_name,
                      SEQ_IN_INDEX AS seq_no, COLUMN_NAME AS column_name
                 FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX""",
            (DATABASE,),
        )
        idx = cur.fetchall()

    groups: dict[str, list[dict]] = {}
    for item in cols:
        table, column = str(item["table_name"]), str(item["column_name"])
        if not IDENTIFIER.fullmatch(table) or not IDENTIFIER.fullmatch(column):
            continue
        vin_match, tech_match = matches(table, column)
        groups.setdefault(table, []).append({
            "name": column,
            "sql_type": str(item["column_type"]),
            "key": str(item["column_key"]),
            "nullable": str(item["is_nullable"]),
            "vin_name_match": vin_match,
            "vehicle_name_match": tech_match,
        })
    indexes: dict[str, dict[str, list[str]]] = {}
    for item in idx:
        table = str(item["table_name"])
        if table not in groups:
            continue
        indexes.setdefault(table, {}).setdefault(str(item["index_name"]), []).append(
            str(item["column_name"])
        )
    estimates = {str(item["table_name"]): int(item["estimated_rows"] or 0)
                 for item in table_rows}
    result = []
    for table, fields in sorted(groups.items()):
        vin_fields = [f["name"] for f in fields if f["vin_name_match"]]
        tech_fields = [f["name"] for f in fields if f["vehicle_name_match"]]
        if not (vin_fields or tech_fields or table in IMPORTANT_TABLES):
            continue
        result.append({
            "table": table, "estimated_rows_not_exact": estimates.get(table),
            "vin_candidate_fields": vin_fields,
            "vehicle_candidate_fields": tech_fields,
            "all_columns": fields,
            "indexes": indexes.get(table, {}),
        })
    return {
        "scope": "LOCAL MYSQL METADATA ONLY; NO ROW CONTENT, NO VIN VALUES",
        "source_database": DATABASE,
        "source_version": str(identity["version"]),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_tables": len(groups),
        "vin_name_candidate_tables": sum(bool(t["vin_candidate_fields"]) for t in result),
        "vehicle_candidate_tables": len(result),
        "tables": result,
        "limitations": [
            "Column names do not prove a table contains individual 17-character VINs.",
            "No VIN values or vehicle attributes were read.",
            "Metadata estimates are approximate, and omitted names can still hide VINs.",
            "Catalogue modification IDs are not equivalent to vehicle VINs.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("vin_source_metadata.json"))
    args = parser.parse_args()
    host = os.getenv("SOURCE_HOST", "127.0.0.1")
    if host not in ("localhost", "127.0.0.1"):
        parser.error("Only local MySQL is allowed (SOURCE_HOST=127.0.0.1)")
    if args.output.exists():
        parser.error("Output exists; choose a fresh filename to preserve prior evidence")
    source = pymysql.connect(
        host=host,
        port=int(os.getenv("SOURCE_PORT", "3306")),
        user=os.getenv("SOURCE_USER", "root"),
        password=os.getenv("SOURCE_PASSWORD", ""),
        database=DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
        connect_timeout=10,
        read_timeout=30,
    )
    try:
        data = inventory(source)
    finally:
        source.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("READ ONLY audit complete; local source unchanged")
    print("Tables inspected:", data["total_tables"])
    print("VIN-name candidate tables:", data["vin_name_candidate_tables"])
    print("Vehicle metadata candidate tables:", data["vehicle_candidate_tables"])
    print("JSON report:", args.output.resolve())
    for item in data["tables"]:
        if item["vin_candidate_fields"]:
            print("VIN candidate:", item["table"], ", ".join(item["vin_candidate_fields"]))
    if data["vin_name_candidate_tables"] == 0:
        print("No VIN-named fields found; this does NOT prove absence of VIN data.")


if __name__ == "__main__":
    main()
