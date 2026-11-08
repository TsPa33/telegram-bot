"""Private, read-only import monitoring dashboard for isolated Catalogue staging."""
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import pymysql

router = APIRouter()
security = HTTPBasic(auto_error=False)

def require_dashboard(credentials: HTTPBasicCredentials | None = Depends(security)):
    password = os.environ.get("CATALOGUE_DASHBOARD_PASSWORD", "")
    username = os.environ.get("CATALOGUE_DASHBOARD_USER", "admin")
    if not password:
        raise HTTPException(status_code=503, detail="Dashboard not configured")
    if (
        credentials is None
        or not secrets.compare_digest(credentials.username.encode(), username.encode())
        or not secrets.compare_digest(credentials.password.encode(), password.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="CarPot Catalogue Monitor"'},
        )

def connection():
    required = ("MYSQLHOST", "MYSQLPORT", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE")
    if any(not os.environ.get(k) for k in required):
        raise HTTPException(status_code=503, detail="Database not configured")
    return pymysql.connect(
        host=os.environ["MYSQLHOST"],
        port=int(os.environ["MYSQLPORT"]),
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5, read_timeout=10, autocommit=True,
    )

@router.get("/monitor", dependencies=[Depends(require_dashboard)], include_in_schema=False)
def monitor():
    return FileResponse(
        "dashboard.html", media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'unsafe-inline'; "
                "style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
            ),
        },
    )

@router.get("/api/v1/import-progress", dependencies=[Depends(require_dashboard)], include_in_schema=False)
def import_progress(response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        with connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT job, processed, updated_at
                   FROM catalogue_import_progress
                   WHERE job IN ('articles','oem-by-article')"""
            )
            rows = cur.fetchall()
            cur.execute(
                """SELECT table_name, table_rows
                   FROM information_schema.tables
                   WHERE table_schema=DATABASE()
                   AND table_name IN ('catalogue_parts','catalogue_oem')"""
            )
            estimated = {r["table_name"]: int(r["table_rows"] or 0) for r in cur.fetchall()}
    except pymysql.MySQLError:
        raise HTTPException(status_code=503, detail="Import progress unavailable")
    progress = {}
    for item in rows:
        timestamp = item["updated_at"]
        if timestamp is not None:
            # MySQL TIMESTAMP returned as naive server-local UTC for staging service.
            timestamp = timestamp.replace(tzinfo=timezone.utc).isoformat()
        progress[item["job"]] = {
            "processed": int(item["processed"]),
            "updated_at": timestamp,
        }
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "jobs": {
            "articles": progress.get("articles", {"processed":0,"updated_at":None}),
            "oem": progress.get("oem-by-article", {"processed":0,"updated_at":None}),
        },
        "approximate_table_rows": {
            "articles": estimated.get("catalogue_parts", 0),
            "oem": estimated.get("catalogue_oem", 0),
        },
        "estimated_source_articles": 5090000,
        "notes": "Checkpoint totals count source records processed. OEM checkpoint counts article groups scanned, not OEM links. Table rows are MySQL estimates.",
    }
