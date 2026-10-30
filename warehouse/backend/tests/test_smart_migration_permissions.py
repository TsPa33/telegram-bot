"""Real non-superuser privileges; separate disposable local databases only."""
import os
import sys
from subprocess import run
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.mark.parametrize('database_create',[False,True])
def test_extension_permissions_and_failed_transaction(database_create):
    admin_url=make_url(os.environ['WAREHOUSE_TEST_DATABASE_URL'])
    assert admin_url.database.endswith('_test')
    admin=create_engine(admin_url,isolation_level='AUTOCOMMIT')
    tag=uuid4().hex
    role='smart_role_'+tag
    database='warehouse_smart_'+tag+'_test'
    # All identifiers below are fixed ASCII prefixes plus uuid4.hex.
    try:
        with admin.connect() as db:
            assert db.scalar(text('SELECT rolsuper FROM pg_roles WHERE rolname=current_user')),'Local test requires administrator to create disposable roles/databases'
            db.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD 'offline-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE"))
            db.execute(text(f'CREATE DATABASE {database}'))
        local_admin=create_engine(admin_url.set(database=database))
        try:
            with local_admin.begin() as db:
                db.execute(text(f'GRANT CREATE, USAGE ON SCHEMA public TO {role}'))
                if database_create:db.execute(text(f'GRANT CREATE ON DATABASE {database} TO {role}'))
            url=admin_url.set(database=database,username=role,password='offline-test-only')
            env={**os.environ,'WAREHOUSE_DATABASE_URL':url.render_as_string(hide_password=False)}
            def alembic(*args):return run([sys.executable,'-m','alembic',*args],env=env,capture_output=True,text=True)
            assert alembic('upgrade','d86f21a90b34').returncode==0
            result=alembic('upgrade','head')
            assert (result.returncode==0)==database_create,result.stderr
            if not database_create:assert 'permission denied' in result.stderr
            with local_admin.connect() as db:
                assert db.scalar(text('SELECT version_num FROM alembic_version'))==('f5c84d31a620' if database_create else 'd86f21a90b34')
                assert db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_trgm')"))==database_create
                assert db.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'ix_%smart_%'"))==(6 if database_create else 0)
            if not database_create:
                # A failed extension install leaves no half-applied migration.
                with local_admin.begin() as db:db.execute(text(f'GRANT CREATE ON DATABASE {database} TO {role}'))
                assert alembic('upgrade','head').returncode==0
            assert alembic('upgrade','head').returncode==0
        finally:local_admin.dispose()
    finally:
        with admin.connect() as db:
            db.execute(text(f'DROP DATABASE IF EXISTS {database} WITH (FORCE)'))
            db.execute(text(f'DROP ROLE IF EXISTS {role}'))
        admin.dispose()
