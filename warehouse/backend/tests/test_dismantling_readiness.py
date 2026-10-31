"""Read-only deployment gate; dedicated local test PostgreSQL, no live API."""
from subprocess import run
import sys
from sqlalchemy import text
from app.db import engine

PATH='/api/v1/dismantling/readiness'


def test_authenticated_gate_is_read_only_and_identifies_contract(client,logged):
    with engine().connect() as db:
        before=db.execute(text('SELECT count(*) FROM operations')).scalar_one()
    r=logged.get(PATH)
    assert r.status_code==200
    assert r.json()=={'status':'ready','feature':'dismantling','contract_version':1,
        'required_revision':'c24a9b71e603','database_revisions':sorted(__import__('app.staging',fromlist=['migration_heads']).migration_heads()),
        'catalog_source':'carpot.base.v1','catalog_items':33}
    with engine().connect() as db:
        assert db.execute(text('SELECT count(*) FROM operations')).scalar_one()==before
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anonymous:assert anonymous.get(PATH).status_code==401


def test_gate_rejects_unmigrated_database(logged):
    run([sys.executable,'-m','alembic','downgrade','b72f03d8e196'],check=True)
    try:assert logged.get(PATH).status_code==503
    finally:run([sys.executable,'-m','alembic','upgrade','head'],check=True)


def test_gate_rejects_missing_table_even_with_current_revision(logged):
    with engine().begin() as db:db.execute(text('ALTER TABLE dismantling_items RENAME TO dismantling_items_offline'))
    try:assert logged.get(PATH).status_code==503
    finally:
        with engine().begin() as db:db.execute(text('ALTER TABLE dismantling_items_offline RENAME TO dismantling_items'))
