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
    import pytest
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.api.dismantling import readiness
    from historical_db import historical_db,seed_inventory,protected
    # Authentication/401 is covered above; exercise the actual route's schema gate
    # against an isolated historical connection, without downgrading shared HEAD.
    with historical_db('b72f03d8e196') as (c,migrate,env):
        seed_inventory(c);before=protected(c)
        isolated=create_engine(env['WAREHOUSE_DATABASE_URL'])
        try:
            with Session(isolated) as db:
                with pytest.raises(HTTPException) as error:readiness(db,None)
                assert error.value.status_code==503
            assert protected(c)==before
            migrate('upgrade','head')
            with Session(isolated) as db:assert readiness(db,None)['status']=='ready'
        finally:isolated.dispose()


def test_gate_rejects_missing_table_even_with_current_revision(logged):
    with engine().begin() as db:db.execute(text('ALTER TABLE dismantling_items RENAME TO dismantling_items_offline'))
    try:assert logged.get(PATH).status_code==503
    finally:
        with engine().begin() as db:db.execute(text('ALTER TABLE dismantling_items_offline RENAME TO dismantling_items'))
