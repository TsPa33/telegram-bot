"""Bounded staging directory refresh, configured independently of staff MFA."""

import json
import logging
import os
import threading
from sqlalchemy import text
from sqlalchemy.orm import Session
from .config import connection, enabled, environment
from .models import SourceState, now
from .projection import sync_batch

log = logging.getLogger("uvicorn.error")


def directory_summary(db):
    """Operational aggregates only: never contacts, source IDs or staff identity."""
    counts = (
        db.execute(
            text("""
        SELECT
          count(*) FILTER (WHERE environment='staging') AS workspaces,
          count(*) FILTER (WHERE environment='preview') AS demo_archived,
          count(*) FILTER (WHERE environment='staging' AND labels::jsonb ? 'Демонстрація') AS demo_in_directory,
          count(*) FILTER (WHERE environment='staging' AND NOT EXISTS (SELECT 1 FROM control_center.source_links l WHERE l.company_id=companies.id AND l.environment='staging' AND l.system='billing' AND l.status='verified')) AS unlinked
        FROM control_center.companies
    """)
        )
        .mappings()
        .one()
    )
    people = (
        db.execute(
            text("""
        SELECT count(*) FILTER (WHERE p->>'role'='DIRECTOR') AS owners,
               count(*) FILTER (WHERE p->>'role'<>'DIRECTOR') AS employees
        FROM control_center.companies c,
             json_array_elements(COALESCE(c.snapshot->'people','[]'::json)) p
        WHERE c.environment='staging'
    """)
        )
        .mappings()
        .one()
    )
    links = (
        db.execute(
            text("""
        SELECT count(*) FILTER (WHERE l.system='warehouse' AND l.status='verified') AS warehouse_links,
               count(*) FILTER (WHERE l.system='billing' AND l.status='verified') AS billing_links,
               count(*) FILTER (WHERE l.status='conflict') AS conflicts,
               count(*) FILTER (WHERE c.id IS NULL OR c.environment<>l.environment) AS invalid_links
        FROM control_center.source_links l
        LEFT JOIN control_center.companies c ON c.id=l.company_id
        WHERE l.environment='staging'
    """)
        )
        .mappings()
        .one()
    )
    state = db.get(SourceState, "warehouse:staging")
    return dict(
        **counts,
        **people,
        **links,
        coverage=state.coverage if state else "incomplete",
        schema_version=state.schema_version if state else None,
        freshness_seconds=int((now() - state.last_success).total_seconds())
        if state and state.last_success
        else None,
        last_success=state.last_success.isoformat()
        if state and state.last_success
        else None,
        last_error=state.last_error if state else None,
    )


def refresh_once():
    if (
        not enabled()
        or environment() != "staging"
        or os.getenv("CONTROL_CENTER_PREVIEW") != "true"
        or not os.getenv("CONTROL_CENTER_WAREHOUSE_SOURCE_URL")
    ):
        return 300
    # Runtime configuration, staging-only transport and its source signature are
    # the authority. Staff login/password/MFA rotation is not a source capability.
    with Session(connection(), expire_on_commit=False) as db:
        state = db.get(SourceState, "warehouse:staging")
        if (
            state
            and state.schema_version != "001"
            and state.coverage == "sweep_complete"
            and state.last_success
            and not state.last_error
            and (now() - state.last_success).total_seconds() < 300
        ):
            return 60
        result = sync_batch(db, 20)
        log.info(
            "control.directory %s", json.dumps(directory_summary(db), sort_keys=True)
        )
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
                # No exception bodies, source payloads, URLs or credentials.
                log.warning("control.directory source_read_failed; retry=60s")
                delay = 60
            stop.wait(delay)

    thread = threading.Thread(target=run, daemon=True, name="control-directory")
    thread.start()
    return stop, thread
