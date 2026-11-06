"""Populated additive parent->head check in a SECOND disposable local DB.
Both URLs must be explicit, loopback, port 55440, and *_test. Never downgrades.
"""

import os, sys, subprocess, json
from sqlalchemy import create_engine, MetaData, Table, select, text
from sqlalchemy.engine import make_url

source = os.environ["WAREHOUSE_TEST_DATABASE_URL"]
target = os.environ["WAREHOUSE_MIGRATION_TEST_URL"]
for raw in (source, target):
    u = make_url(raw)
    if u.host != "127.0.0.1" or u.port != 55440 or not u.database.endswith("_test"):
        raise RuntimeError("Dedicated local DB required")
if source == target:
    raise RuntimeError("Separate target required")
env = {
    **os.environ,
    "WAREHOUSE_DATABASE_URL": target,
    "WAREHOUSE_CATALOGUE_WORKER_ENABLED": "false",
}


def migrate(revision):
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision], env=env, check=True
    )


migrate("ac97f052e1b4")
a = create_engine(source)
b = create_engine(target)
tables = [
    "accounts",
    "vehicles",
    "categories",
    "subcategories",
    "parts",
    "operations",
    "vehicle_checklist_items",
    "plan_parts_article_receipts",
]
before = {}
with a.connect() as src, b.begin() as dst:
    for name in tables:
        if not __import__("sqlalchemy").inspect(b).has_table(name):
            continue
        old = Table(name, MetaData(), autoload_with=b)
        current = Table(name, MetaData(), autoload_with=a)
        rows = [
            dict(r)
            for r in src.execute(
                select(*(current.c[c.name] for c in old.columns))
            ).mappings()
        ]
        if rows:
            dst.execute(old.insert(), rows)
        before[name] = rows
assert before["parts"] and before["plan_parts_article_receipts"], "Seed data required"
migrate("head")
migrate("head")
with b.connect() as db:
    for name, rows in before.items():
        table = Table(name, MetaData(), autoload_with=b)
        cols = list(rows[0]) if rows else [c.name for c in table.columns]
        after = [
            dict(r) for r in db.execute(select(*(table.c[k] for k in cols))).mappings()
        ]
        assert sorted(map(str, after)) == sorted(map(str, rows)), name
    assert db.scalar(text("SELECT version_num FROM alembic_version")) == "bd18a9f37c20"
    assert db.scalar(text("SELECT count(*) FROM plan_parts_responses")) == 0
print(
    json.dumps(
        dict(
            parent="ac97f052e1b4",
            head="bd18a9f37c20",
            old_columns_unchanged={k: len(v) for k, v in before.items()},
            startup_repeat="PASS",
            new_api_requests=0,
        ),
        indent=2,
    )
)
