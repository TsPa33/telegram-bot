import os
from functools import lru_cache
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def enabled():
    return os.getenv("CONTROL_CENTER_ENABLED", "false") == "true"


def environment():
    value = os.getenv("CONTROL_CENTER_SOURCE_ENVIRONMENT", "")
    if value not in {"local", "staging", "production"}:
        raise RuntimeError("Explicit Control Center source environment required")
    return value


def password_only():
    """Explicit opt-in, bound to the actual non-production runtime identity."""
    if os.getenv("CONTROL_CENTER_AUTH_MODE", "mfa") != "password-only":
        return False
    env = environment()
    runtime = os.getenv("RAILWAY_ENVIRONMENT_NAME", "")
    runtime_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "")
    if env == "local":
        return (
            not runtime
            and not runtime_id
            and urlsplit(origin()).hostname in {"localhost", "127.0.0.1", "testserver"}
        )
    expected_id = os.getenv("CONTROL_CENTER_PASSWORD_ONLY_ENVIRONMENT_ID", "")
    return (
        env == "staging"
        and runtime == "warehouse-staging"
        and bool(expected_id)
        and runtime_id == expected_id
    )


def auth_mode():
    return "password-only" if password_only() else "mfa"


def origin():
    value = os.getenv("CONTROL_CENTER_ORIGIN", "")
    p = urlsplit(value)
    local = environment() == "local" and p.hostname in {
        "localhost",
        "127.0.0.1",
        "testserver",
    }
    if (
        p.scheme not in ({"http", "https"} if local else {"https"})
        or not p.netloc
        or p.username
        or p.password
        or p.path
        or p.query
        or p.fragment
    ):
        raise RuntimeError("Exact Control Center origin required")
    return value


def cipher():
    # No fallback, not inherited from customer or provider secrets.
    return Fernet(os.environ["CONTROL_CENTER_MFA_KEY"].encode())


@lru_cache
def connection(name="CONTROL_CENTER_DATABASE_URL"):
    value = os.environ[name]
    u = make_url(value)
    if u.drivername != "postgresql+psycopg":
        raise RuntimeError("Control Center requires PostgreSQL psycopg")
    if (
        u.host not in {"127.0.0.1", "localhost"}
        and u.query.get("sslmode") != "verify-full"
    ):
        raise RuntimeError("Remote PostgreSQL requires verify-full TLS")
    engine = create_engine(
        value,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
        connect_args={
            "options": "-c statement_timeout=5000 -c lock_timeout=3000",
            "connect_timeout": 3,
        },
    )
    if name == "CONTROL_CENTER_DATABASE_URL":

        @event.listens_for(engine, "connect")
        def runtime_guard(raw, record):
            with raw.cursor() as c:
                c.execute(
                    "SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user"
                )
                if any(c.fetchone()):
                    raise RuntimeError(
                        "Control Center runtime must be an unprivileged role"
                    )
                c.execute(
                    "SELECT pg_has_role(current_user,nspowner,'MEMBER') FROM pg_namespace WHERE nspname='control_center'"
                )
                row = c.fetchone()
                if not row or row[0]:
                    raise RuntimeError("Control Center runtime cannot own its schema")
                c.execute(
                    "SELECT version,environment FROM control_center.schema_version"
                )
                if c.fetchone() != ("001", environment()):
                    raise RuntimeError("Control Center schema/environment mismatch")
            raw.rollback()

    if name == "CONTROL_CENTER_WAREHOUSE_READ_URL":

        @event.listens_for(engine, "connect")
        def source_guard(raw, record):
            with raw.cursor() as c:
                c.execute(
                    "SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user"
                )
                if any(c.fetchone()):
                    raise RuntimeError("Warehouse reader must be an unprivileged role")
                c.execute(
                    "SELECT has_table_privilege(current_user,'public.accounts','INSERT,UPDATE,DELETE,TRUNCATE')"
                )
                if c.fetchone()[0]:
                    raise RuntimeError(
                        "Warehouse reader cannot write customer accounts"
                    )
                c.execute(
                    "SELECT pg_has_role(current_user,relowner,'MEMBER') FROM pg_class WHERE oid='public.accounts'::regclass"
                )
                if c.fetchone()[0]:
                    raise RuntimeError(
                        "Warehouse reader cannot inherit the source owner"
                    )
                c.execute(
                    "SELECT has_column_privilege(current_user,'public.accounts','password_hash','SELECT')"
                )
                if c.fetchone()[0]:
                    raise RuntimeError("Warehouse reader cannot read password hashes")
            raw.rollback()

    return engine


def get_db():
    with Session(connection(), expire_on_commit=False) as db:
        yield db
