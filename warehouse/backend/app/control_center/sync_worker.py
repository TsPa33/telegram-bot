"""Bounded automatic staging directory refresh after owner security rotation."""
import os
import threading
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import connection, enabled, environment
from .models import Audit, Staff, SourceState, now
from .projection import sync_batch

def refresh_once():
    if not enabled() or environment() != "staging" or os.getenv("CONTROL_CENTER_PREVIEW") != "true" or not os.getenv("CONTROL_CENTER_WAREHOUSE_SOURCE_URL"):
        return 300
    with Session(connection(), expire_on_commit=False) as db:
        rotated = db.scalar(select(Audit.id).join(Staff, Staff.id == Audit.actor).where(
            Audit.permission == "auth.rotate", Staff.role == "Owner", Staff.active.is_(True)
        ).limit(1))
        if not rotated:
            return 15
        state = db.get(SourceState, "warehouse:staging")
        if state and state.schema_version != "001" and state.coverage == "sweep_complete" and state.last_success and not state.last_error and (now()-state.last_success).total_seconds() < 300:
            return 60
        result = sync_batch(db, 20)
        return 5 if result["next_cursor"] else 300

def start():
    stop = threading.Event()
    if os.getenv("CONTROL_CENTER_AUTO_SYNC") != "true":
        return stop, None
    def run():
        while not stop.is_set():
            try:
                delay = refresh_once()
            except Exception:
                delay = 60
            stop.wait(delay)
    thread = threading.Thread(target=run, daemon=True, name="control-directory")
    thread.start()
    return stop, thread
