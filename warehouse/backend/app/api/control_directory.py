"""Staff-directory export. Staging only, explicit peer authentication, SELECT-only."""
import os
from fastapi import APIRouter, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import is_staging
from app.db import engine
from app.services.control_transport import authorized, PATH
from app.services.control_directory import read_batch

router = APIRouter()

@router.get(PATH, include_in_schema=False)
def directory(cursor: str = Query("", max_length=160), limit: int = Query(20, ge=1, le=50),
              x_control_stamp: str = Header("", max_length=20),
              x_control_signature: str = Header("", max_length=64)):
    if not is_staging() or os.getenv("WAREHOUSE_CONTROL_DIRECTORY_ENABLED") != "true":
        raise HTTPException(404)
    if not authorized(os.getenv("WAREHOUSE_CONTROL_DIRECTORY_KEY", ""), x_control_stamp, cursor, limit, x_control_signature):
        raise HTTPException(401, "Invalid service proof")
    try:
        with Session(engine()) as db:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = '5s'"))
            db.execute(text("SET LOCAL lock_timeout = '2s'"))
            records, next_cursor = read_batch(db, cursor or None, limit, "staging")
            return {"environment": "staging", "records": records, "next_cursor": next_cursor}
    except Exception:
        raise HTTPException(503, "Directory temporarily unavailable") from None
