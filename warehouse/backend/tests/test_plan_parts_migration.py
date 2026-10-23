"""Dedicated warehouse*_test DB ONLY, using the existing guarded fixtures."""
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import staging
from app.db import engine


def test_existing_donor_survives_upgrade_via_staging_startup(vehicle):
    with engine().connect() as conn:
        before = dict(conn.execute(text("SELECT * FROM vehicles WHERE id=:id"), {"id": vehicle["id"]}).mappings().one())
        audit_before = conn.execute(text("SELECT count(*) FROM operations")).scalar_one()
    # Recreate the pre-integration schema; the existing donor and audit remain.
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "f482ab1376c0"], check=True)
    try:
        with engine().connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "f482ab1376c0"
            assert conn.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name='vehicles' AND column_name='ktype'")).scalar_one() == 0
        # Exact migration function used by app.staging before serving traffic.
        staging.migrate(timeout=10)
        staging.migrate(timeout=10)  # Startup retry must be idempotent.
        with engine().connect() as conn:
            after = dict(conn.execute(text("SELECT * FROM vehicles WHERE id=:id"), {"id": vehicle["id"]}).mappings().one())
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "f06a41c9d2b7"
            assert conn.execute(text("SELECT count(*) FROM operations")).scalar_one() == audit_before
        assert after == before
        assert after["ktype"] is None
        with engine().begin() as conn:
            conn.execute(text("UPDATE vehicles SET ktype=16063 WHERE id=:id"), {"id": vehicle["id"]})
        with engine().begin() as conn:
            conn.execute(text("UPDATE vehicles SET ktype=NULL WHERE id=:id"), {"id": vehicle["id"]})
        with pytest.raises(IntegrityError):
            with engine().begin() as conn:
                conn.execute(text("UPDATE vehicles SET ktype=0 WHERE id=:id"), {"id": vehicle["id"]})
    finally:
        # Keep fixtures usable even if an assertion fails before migration.
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
