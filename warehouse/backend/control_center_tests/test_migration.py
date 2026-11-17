import os
from sqlalchemy import text
import pytest
from sqlalchemy.exc import DBAPIError
from app.control_center.config import connection
from app.control_center.manage import migrate, provision
from app.control_center.models import Staff, Session, now
from app.control_center.security import digest
from datetime import timedelta
from test_support import SECRET


def test_migration_repeatable_and_runtime_permissions(db, monkeypatch):
    monkeypatch.setenv(
        "CONTROL_CENTER_MIGRATOR_URL", os.environ["CONTROL_CENTER_TEST_ADMIN_URL"]
    )
    migrate()
    migrate()
    with connection().connect() as c:
        assert (
            c.scalar(text("SELECT version FROM control_center.schema_version")) == "002"
        )
    for sql in [
        "CREATE TABLE control_center.forbidden(id int)",
        "UPDATE control_center.schema_version SET version='tamper'",
        "DELETE FROM control_center.audit",
        "TRUNCATE control_center.audit",
    ]:
        with pytest.raises(DBAPIError):
            with connection().begin() as c:
                c.execute(text(sql))
    monkeypatch.setenv("CONTROL_CENTER_SOURCE_ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="mismatch"):
        migrate()


def test_owner_provision_requires_mfa_and_no_default_secret(db, monkeypatch):
    with pytest.raises(ValueError, match="confirmation"):
        provision(db, "owner", "Owner", "long-operator-password", SECRET, "bad")
    monkeypatch.delenv("CONTROL_CENTER_MFA_KEY")
    from app.control_center.config import cipher

    with pytest.raises(KeyError):
        cipher()
