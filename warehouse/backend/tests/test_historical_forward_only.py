"""Exercise each history refusal at its immediate boundary, with real PostgreSQL."""

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from historical_db import historical_db, seed_inventory, insert, protected


@pytest.mark.parametrize(
    "revision,parent,source,job_type,message",
    [
        (
            "c8f21d6e903a",
            "b7e14d90c2f6",
            "file",
            "file_validation",
            "Runner history exists",
        ),
        (
            "d3a82f1c904b",
            "c8f21d6e903a",
            "aleto_fixture",
            "aleto_offline",
            "Adapter history exists",
        ),
        (
            "e4b93a2d715c",
            "d3a82f1c904b",
            "partline_fixture",
            "partline_fixture",
            "PartLine fixture history exists",
        ),
    ],
)
def test_queue_history_refuses_its_own_downgrade(
    revision, parent, source, job_type, message
):
    with historical_db(revision) as (c, migrate, env):
        ids = seed_inventory(c)
        insert(
            c,
            "import_jobs",
            dict(
                id=str(uuid4()),
                account_id=ids["owner"],
                created_by=ids["owner"],
                source=source,
                job_type=job_type,
                parameters={},
                status="completed",
                created_at=datetime.now(timezone.utc),
                progress_current=1,
                progress_total=1,
                phase="complete",
                result_summary={"synthetic": True},
                attempt_count=1,
                retry_count=0,
                event_count=0,
                idempotency_key=str(uuid4()),
                fingerprint="a" * 64,
                context_hash="b" * 64,
            ),
        )
        before = protected(c)
        result = migrate("downgrade", parent, check=False)
        assert result.returncode != 0 and message in result.stderr
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (
            revision,
        )
        assert protected(c) == before


def test_vin_evidence_downgrade_is_unconditionally_forward_only():
    with historical_db("08b72c9d4e16") as (c, migrate, env):
        seed_inventory(c)
        before = protected(c)
        result = migrate("downgrade", "f7a10b8c43d2", check=False)
        assert (
            result.returncode != 0
            and "Forward-only VIN evidence migration" in result.stderr
        )
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "08b72c9d4e16",
        )
        assert protected(c) == before


def test_entitlement_projection_history_refuses_destructive_downgrade():
    with historical_db("a12b34c56d78") as (c, migrate, env):
        ids = seed_inventory(c)
        insert(
            c,
            "warehouse_entitlement_workspaces",
            dict(
                workspace_id=ids["owner"],
                owner_id=ids["owner"],
                billing_account_id=str(uuid4()),
            ),
        )
        before = protected(c)
        result = migrate("downgrade", "08b72c9d4e16", check=False)
        assert (
            result.returncode != 0
            and "Preserve projection, provenance and returns" in result.stderr
        )
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "a12b34c56d78",
        )
        assert protected(c) == before


def test_global_billing_upgrade_preserves_populated_projection_and_refuses_rollback():
    with historical_db('a12b34c56d78') as (c,migrate,env):
        ids=seed_inventory(c)
        insert(c,'warehouse_entitlement_workspaces',dict(workspace_id=ids['owner'],owner_id=ids['owner'],billing_account_id=str(uuid4()),version=7,intervals=[]))
        before=protected(c)
        projection=c.execute('SELECT row_to_json(w) FROM warehouse_entitlement_workspaces w').fetchone()[0]
        migrate('upgrade','head')
        from psycopg import sql
        for table,(names,rows) in before.items():
            query=sql.SQL('SELECT {} FROM {} ORDER BY 1').format(sql.SQL(',').join(map(sql.Identifier,names)),sql.Identifier(table))
            assert c.execute(query).fetchall()==rows,table
        after=c.execute('SELECT row_to_json(w) FROM warehouse_entitlement_workspaces w').fetchone()[0]
        assert after.pop('source_environment')=='test' and after.pop('global_binding_id') is None
        assert after==projection
        upgraded=protected(c)
        refused=migrate('downgrade','a12b34c56d78',check=False)
        assert refused.returncode!=0 and 'Preserve canonical Billing identities and snapshots; roll forward or disable routing' in refused.stderr
        assert c.execute('SELECT version_num FROM alembic_version').fetchone()==('b23c45d67e89',)
        assert protected(c)==upgraded
