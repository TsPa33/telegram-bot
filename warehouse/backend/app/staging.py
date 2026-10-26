"""Fail-closed staging startup: validate, migrate under a DB lock, then serve."""

import logging
import os
from pathlib import Path
import pwd
import socket
import time
from functools import lru_cache

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool
import uvicorn

from app.config import database_url, photo_dir, public_origin, secure_cookies

log = logging.getLogger("warehouse.staging")
ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LOCK = 0x57415245484F5553


def alembic_config():
    return Config(str(ROOT / "alembic.ini"))


@lru_cache
def migration_heads():
    return frozenset(ScriptDirectory.from_config(alembic_config()).get_heads())


def schema_supports(required, versions):
    if frozenset(versions) != migration_heads():
        return False
    scripts=ScriptDirectory.from_config(alembic_config())
    return all(required in {r.revision for r in scripts.iterate_revisions(head,'base')} for head in versions)


def migrate(timeout=120):
    """One session lock covers the whole upgrade, across concurrent deploys.

    Commit lock-acquisition's implicit transaction before Alembic starts its own
    transaction. A session advisory lock survives commits and releases on crash.
    """
    deadline = time.monotonic() + timeout
    db_engine = sa.create_engine(
        database_url(), poolclass=NullPool, connect_args={"connect_timeout": 5}
    )
    connection = None
    try:
        while connection is None:
            try:
                connection = db_engine.connect()
            except OperationalError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Warehouse staging database not reachable within startup timeout"
                    ) from None
                time.sleep(1)
        while True:
            locked = connection.execute(
                sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": MIGRATION_LOCK}
            ).scalar_one()
            connection.commit()
            if locked:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Warehouse migration lock timeout; another startup is migrating"
                )
            time.sleep(0.25)
        log.info("Applying Warehouse migrations under exclusive advisory lock")
        config = alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        log.info("Warehouse migrations complete")
    finally:
        if connection is not None:
            # Closing also releases the session lock, even if upgrade raised.
            connection.close()
        db_engine.dispose()


def drop_volume_bootstrap_privileges():
    """Optional Railway volume bootstrap; the API itself always runs non-root.

    Railway mounts volumes as root. With a photo volume ONLY, operators can set
    RAILWAY_RUN_UID=0. Adjust its root ownership and immediately drop privileges.
    Never recursively chown files or change ownership outside /data/photos.
    """
    folder = photo_dir()
    if os.geteuid() == 0:
        user = pwd.getpwnam("warehouse")
        if folder is not None:
            if folder != Path("/data/photos") or folder.is_symlink():
                raise RuntimeError("Root photo bootstrap only supports /data/photos")
            folder.mkdir(parents=True, exist_ok=True)
            os.chown(folder, user.pw_uid, user.pw_gid)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    if folder is not None:
        folder.mkdir(parents=True, exist_ok=True)
        if not os.access(folder, os.W_OK):
            raise RuntimeError(
                "Warehouse photo volume is not writable; see Railway staging volume instructions"
            )


def main():
    logging.basicConfig(level=logging.INFO)
    if os.getenv("WAREHOUSE_ENV") != "staging":
        raise RuntimeError("Staging entrypoint requires WAREHOUSE_ENV=staging")
    if not secure_cookies():
        raise RuntimeError("Staging requires WAREHOUSE_COOKIE_SECURE=true")
    public_origin()  # Validate before touching a database.
    database_url()
    port = int(os.getenv("PORT", "8010"))
    timeout = int(os.getenv("WAREHOUSE_STARTUP_TIMEOUT", "120"))
    if not 1024 <= port <= 65535 or not 10 <= timeout <= 600:
        raise RuntimeError("Invalid staging PORT or startup timeout")
    drop_volume_bootstrap_privileges()
    migrate(timeout)
    # Dual-stack works in both new IPv4/IPv6 Railway environments and legacy
    # IPv6-only private networks; also accepts IPv4 deployment health checks.
    listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    listener.bind(("::", port))
    listener.listen(128)
    config = uvicorn.Config(
        "app.main:app",
        host="::",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv(
            "WAREHOUSE_FORWARDED_ALLOW_IPS", "fd00::/8,10.0.0.0/8"
        ),
        workers=1,
        access_log=False,
        timeout_graceful_shutdown=30,
    )
    uvicorn.Server(config).run(sockets=[listener])


if __name__ == "__main__":
    main()
