"""Fresh historical schemas, never destructive downgrade of the shared HEAD test DB."""

from contextlib import contextmanager
from datetime import datetime, date, timezone
from decimal import Decimal
import os, subprocess, sys
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url


def require_local(url):
    parsed = make_url(url)
    if parsed.host not in ("127.0.0.1", "localhost", "::1") or not (
        parsed.database or ""
    ).endswith("_test"):
        raise RuntimeError(
            "Historical migration fixtures require explicit loopback *_test PostgreSQL"
        )
    return parsed


@contextmanager
def historical_db(revision):
    source = require_local(os.environ["WAREHOUSE_TEST_DATABASE_URL"])
    name = "warehouse_history_" + uuid4().hex + "_test"
    admin = dict(
        host=source.host,
        port=source.port or 5432,
        user=source.username,
        password=source.password,
        dbname=source.database,
    )
    with psycopg.connect(**admin, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = source.set(database=name).render_as_string(hide_password=False)
    env = {
        **os.environ,
        "WAREHOUSE_DATABASE_URL": url,
        "WAREHOUSE_TEST_DATABASE_URL": url,
        "WAREHOUSE_ENV": "local",
        "WAREHOUSE_ENTITLEMENTS_ENABLED": "false",
        "WAREHOUSE_CATALOGUE_WORKER_ENABLED": "false",
    }
    try:

        def migrate(*args, check=True):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *args],
                env=env,
                capture_output=True,
                text=True,
            )
            if check and result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            return result

        migrate("upgrade", revision)
        with psycopg.connect(
            **{**admin, "dbname": name}, autocommit=True
        ) as connection:
            yield connection, migrate, env
    finally:
        with psycopg.connect(**admin, autocommit=True) as c:
            c.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def columns(c, table):
    return {
        r[0]
        for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
    }


def insert(c, table, values):
    available = columns(c, table)
    payload = {k: v for k, v in values.items() if k in available}
    keys = list(payload)
    c.execute(
        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, keys)),
            sql.SQL(",").join(sql.Placeholder() for _ in keys),
        ),
        [Jsonb(v) if isinstance(v, (dict, list)) else v for v in payload.values()],
    )


def seed_inventory(c, *, unknown_date=False):
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner, vehicle, part, receipt, sale, reserve = [str(uuid4()) for _ in range(6)]
    insert(
        c,
        "accounts",
        dict(
            id=owner,
            email="historical@example.test",
            name="Historical owner",
            password_hash="synthetic-no-login",
            created_at=stamp,
            role="DIRECTOR",
            permissions=[],
            is_active=True,
            must_change_password=False,
        ),
    )
    insert(
        c,
        "vehicles",
        dict(
            id=vehicle,
            account_id=owner,
            manufacturer="TEST",
            model="Historical donor",
            generation="",
            year=2020,
            engine="",
            fuel_type="",
            transmission="",
            vin="VF1AAAAA000000001",
            donor_id="HISTORY-001",
            number=1,
            acquisition_cost=Decimal("100.00"),
            acquisition_date=None if unknown_date else date(2026, 1, 1),
            notes="Preserve VIN and donor",
            status="dismantling",
            archived=False,
            created_at=stamp,
            dismantling_v3={},
            vin_details={"source": "synthetic history"},
        ),
    )
    insert(
        c,
        "parts",
        dict(
            id=part,
            account_id=owner,
            vehicle_id=vehicle,
            name="Historical stock",
            oem_number="HIST-OEM",
            article_number="",
            article_brand="",
            quantity=4,
            reserved_quantity=1,
            unit_cost=Decimal("10.00"),
            selling_price=Decimal("50.00"),
            currency="UAH",
            location="A1",
            compatibility_notes="",
            description="",
            internal_notes="",
            availability="present",
            condition="used",
            individually_tracked=False,
            archived=False,
            created_at=stamp,
            assortment_enabled=True,
            inventory_origin="legacy",
            quantity_basis="verified",
            physical_location_kind="on_shelf",
        ),
    )
    for identity, kind, before, after in [
        (
            receipt,
            "receipt",
            {"quantity": 0, "reserved_quantity": 0},
            {"quantity": 5, "reserved_quantity": 0},
        ),
        (
            sale,
            "sale",
            {"quantity": 5, "reserved_quantity": 0},
            {
                "quantity": 4,
                "reserved_quantity": 0,
                "sale": {
                    "version": 1,
                    "source": "quick",
                    "quantity": 1,
                    "unit_price": "50.00",
                    "currency": "UAH",
                    "total": "50.00",
                },
            },
        ),
        (
            reserve,
            "reserve",
            {"quantity": 4, "reserved_quantity": 0},
            {"quantity": 4, "reserved_quantity": 1},
        ),
    ]:
        insert(
            c,
            "operations",
            dict(
                id=identity,
                account_id=owner,
                actor_id=owner,
                part_id=part,
                vehicle_id=vehicle,
                entity_id=part,
                entity_type="parts",
                type=kind,
                reason="Historical synthetic operation",
                before=before,
                after=after,
                created_at=stamp,
            ),
        )
    if columns(c, "orders"):
        buyer, order, line, reservation, event = [str(uuid4()) for _ in range(5)]
        insert(
            c,
            "buyers",
            dict(
                id=buyer,
                account_id=owner,
                name="Historical buyer",
                phone="0501234567",
                phone_normalized="380501234567",
                additional_phone="",
                additional_phone_normalized="",
                notes="",
                created_at=stamp,
                updated_at=stamp,
            ),
        )
        insert(
            c,
            "orders",
            dict(
                id=order,
                account_id=owner,
                number=1,
                buyer_id=buyer,
                contact_name="Historical buyer",
                contact_phone="0501234567",
                contact_phone_normalized="380501234567",
                status="reserved",
                delivery_method="pickup",
                city="",
                delivery_address="",
                tracking_number="",
                notes="",
                created_at=stamp,
                updated_at=stamp,
            ),
        )
        insert(
            c,
            "order_lines",
            dict(
                id=line,
                account_id=owner,
                order_id=order,
                part_id=part,
                name="Historical stock",
                quantity=1,
                unit_price=Decimal("20.00"),
                currency="UAH",
                line_total=Decimal("20.00"),
                donor_snapshot={},
                active=True,
                created_at=stamp,
            ),
        )
        insert(
            c,
            "order_reservations",
            dict(
                id=reservation,
                account_id=owner,
                order_line_id=line,
                part_id=part,
                quantity=1,
                reserve_operation_id=reserve,
                state="active",
                created_at=stamp,
            ),
        )
        insert(
            c,
            "order_events",
            dict(
                id=event,
                account_id=owner,
                actor_id=owner,
                order_id=order,
                type="created",
                data={"synthetic": True},
                created_at=stamp,
            ),
        )
    return dict(owner=owner, vehicle=vehicle, part=part, sale=sale, reserve=reserve)


def protected(c):
    tables = [
        r[0]
        for r in c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version' ORDER BY tablename"
        )
    ]
    return {
        t: (
            [
                r[0]
                for r in c.execute(
                    sql.SQL("SELECT * FROM {} LIMIT 0").format(sql.Identifier(t))
                ).description
            ],
            c.execute(
                sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(t))
            ).fetchall(),
        )
        for t in tables
        if columns(c, t)
    }


def assert_historical_upgrade(start, target="head", *, copy_fixture=True, verify=None):
    with historical_db(start) as (c, migrate, env):
        ids = seed_inventory(c)
        if copy_fixture:
            copy_current_fixture(c)
        before = protected(c)
        migrate("upgrade", target)
        migrate("upgrade", target)
        for table, (names, rows) in before.items():
            result = c.execute(
                sql.SQL("SELECT {} FROM {} ORDER BY 1").format(
                    sql.SQL(",").join(map(sql.Identifier, names)), sql.Identifier(table)
                )
            ).fetchall()
            assert result == rows, (start, target, table)
        assert c.execute(
            "SELECT quantity,reserved_quantity FROM parts WHERE id=%s", (ids["part"],)
        ).fetchone() == (4, 1)
        assert (
            c.execute(
                "SELECT vin FROM vehicles WHERE id=%s", (ids["vehicle"],)
            ).fetchone()[0]
            == "VF1AAAAA000000001"
        )
        assert (
            c.execute("SELECT count(*) FROM operations WHERE type='sale'").fetchone()[0]
            >= 1
        )
        if verify:
            verify(c, ids)
        if target == "head":
            migrate("check")
        return ids


def copy_current_fixture(c):
    """Copy synthetic compatible columns with all constraints/triggers enabled.

    No schema downgrade, replication-role change or mocked migration success. Nullable
    activation backreferences are restored after their referenced operation is inserted.
    """
    source = require_local(os.environ["WAREHOUSE_TEST_DATABASE_URL"])
    kwargs = dict(
        host=source.host,
        port=source.port or 5432,
        user=source.username,
        password=source.password,
        dbname=source.database,
    )
    with c.transaction(), psycopg.connect(**kwargs, autocommit=True) as current:
        tables = {
            r[0]
            for r in c.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )
        } - {"alembic_version"}
        dependencies = {t: set() for t in tables}
        for child, parent, column in c.execute(
            """SELECT t.relname,p.relname,a.attname FROM pg_constraint k
            JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_class p ON p.oid=k.confrelid JOIN LATERAL unnest(k.conkey) key(attnum) ON true
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=key.attnum
            WHERE k.contype='f' AND n.nspname='public'""".replace("+", "")
        ):
            if child != parent and not (
                child == "parts" and column == "activation_operation_id"
            ):
                dependencies[child].add(parent)
        ordered = []
        while len(ordered) < len(tables):
            ready = sorted(
                t for t in tables - set(ordered) if dependencies[t] <= set(ordered)
            )
            if not ready:
                raise AssertionError(("Unresolved fixture FK order", dependencies))
            ordered.extend(ready)
        deferred = []
        for table in ordered:
            shared = sorted(columns(c, table) & columns(current, table))
            if not shared:
                continue
            records = current.execute(
                sql.SQL("SELECT {} FROM {}").format(
                    sql.SQL(",").join(map(sql.Identifier, shared)),
                    sql.Identifier(table),
                )
            ).fetchall()
            data = [dict(zip(shared, row)) for row in records]
            if "id" in shared:
                byid = {row["id"]: row for row in data}
                done = set()
                sorted_rows = []

                def append(row):
                    if row["id"] in done:
                        return
                    for key in ("parent_id", "workspace_account_id"):
                        if row.get(key) in byid:
                            append(byid[row[key]])
                    done.add(row["id"])
                    sorted_rows.append(row)

                for row in data:
                    append(row)
                data = sorted_rows
            for row in data:
                if table == "parts" and row.get("activation_operation_id"):
                    deferred.append((row["activation_operation_id"], row["id"]))
                    row["activation_operation_id"] = None
            query = sql.SQL(
                "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(table),
                sql.SQL(",").join(map(sql.Identifier, shared)),
                sql.SQL(",").join(sql.Placeholder() for _ in shared),
            )
            with c.cursor() as cursor:
                cursor.executemany(
                    query,
                    [
                        [
                            Jsonb(row[k])
                            if isinstance(row[k], (dict, list))
                            else row[k]
                            for k in shared
                        ]
                        for row in data
                    ],
                )
        with c.cursor() as cursor:
            cursor.executemany(
                "UPDATE parts SET activation_operation_id=%s WHERE id=%s", deferred
            )
