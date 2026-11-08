"""Create compact tables only in the isolated staging MySQL database."""
import os
import pymysql

required = ("MYSQLHOST", "MYSQLPORT", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE")
missing = [key for key in required if not os.getenv(key)]
if missing:
    raise SystemExit("Missing DB env vars: " + ", ".join(missing))
conn = pymysql.connect(
    host=os.environ["MYSQLHOST"],
    port=int(os.environ["MYSQLPORT"]),
    user=os.environ["MYSQLUSER"],
    password=os.environ["MYSQLPASSWORD"],
    database=os.environ["MYSQLDATABASE"],
    charset="utf8mb4",
    connect_timeout=10,
)
try:
    with conn.cursor() as cur:
        with open("schema.sql", encoding="utf-8") as fh:
            statements = "\n".join(
                line for line in fh if not line.lstrip().startswith("--")
            ).split(";")
        for statement in statements:
            if statement.strip():
                cur.execute(statement)
    conn.commit()
    print("CarPot Catalogue compact schema ready")
finally:
    conn.close()
