"""Forward-only upgrade on a populated, separate disposable local PostgreSQL."""

import os, sys, json, hashlib, subprocess
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

url = os.environ["WAREHOUSE_UPGRADE_TEST_URL"]
u = make_url(url)
if u.host != "127.0.0.1" or u.port != 55440 or not u.database.endswith("_test"):
    raise RuntimeError("Explicit local disposable DB required")
e = create_engine(url)


def hashes():
    with e.connect() as c:
        return {
            t: hashlib.sha256(
                json.dumps(
                    sorted(
                        json.dumps(dict(r), sort_keys=True, default=str)
                        for r in c.execute(text('SELECT * FROM "' + t + '"')).mappings()
                    )
                ).encode()
            ).hexdigest()
            for t in inspect(e).get_table_names()
            if t != "alembic_version"
        }


with e.connect() as c:
    assert (
        c.scalar(text("SELECT version_num FROM alembic_version")) == "c4197e2a8d60"
    ), "Expected populated parent, never downgrade"
    assert (
        c.scalar(text("SELECT count(*) FROM parts")) > 0
    ), "Populated stock proof required"
before = hashes()
env = {
    **os.environ,
    "WAREHOUSE_DATABASE_URL": url,
    "WAREHOUSE_CATALOGUE_WORKER_ENABLED": "false",
}
for _ in range(2):
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True
    )
after = hashes()
assert all(after[k] == v for k, v in before.items())
with e.connect() as c:
    assert c.scalar(text("SELECT version_num FROM alembic_version")) == "d5298f3b7a10"
    for t in ("source_type_mappings",):
        assert c.scalar(text("SELECT count(*) FROM " + t)) == 0
print(
    json.dumps(
        {
            "parent": "c4197e2a8d60",
            "head": "d5298f3b7a10",
            "old_tables_unchanged": len(before),
            "new_tables_empty": True,
            "repeated_upgrade": "PASS",
        }
    )
)
