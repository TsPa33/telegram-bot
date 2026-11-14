"""Synthetic cross-service product acceptance with real isolated PostgreSQL projection."""

import asyncio, json, os
from pathlib import Path
import httpx
from psycopg2.extensions import parse_dsn
from bot.billing.tests.test_operational import operational, callback, KEY
from bot.billing.client import BillingClient
from bot.billing.api import create_app


def test_telegram_garage_projection_and_flags_off(operational, monkeypatch):
    import asyncpg
    from bot.database import pool as pool_module
    from bot.services import global_billing as gb

    core, payments, p, _, _, _ = operational
    core.seed_catalogue()
    monkeypatch.setenv("BOT_BILLING_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("BOT_BILLING_DEPLOYMENT", "local")
    monkeypatch.setenv("BOT_GLOBAL_GARAGE_ENABLED", "true")
    monkeypatch.setenv("BILLING_PUBLIC_ORIGIN", "https://billing.example.test")
    monkeypatch.setenv(
        "BILLING_PUBLIC_LINK_KEY", "synthetic-product-public-links-key-123456789"
    )
    app = create_app(
        core.db, p.profile, peer_keys={"telegram": KEY}, checkout_enabled=True
    )
    sdk = BillingClient(
        "https://billing.example.test",
        KEY,
        "telegram",
        "sandbox",
        transport=httpx.ASGITransport(app=app),
    )
    monkeypatch.setattr(gb, "client", lambda: sdk)

    async def scenario():
        dsn = parse_dsn(os.environ["CARPOT_BILLING_PROJECTION_TEST_DSN"])
        pool = await asyncpg.create_pool(
            host=dsn["host"],
            port=int(dsn.get("port", 5432)),
            database=dsn["dbname"],
            user=dsn["user"],
            password=dsn["password"],
            min_size=1,
            max_size=3,
        )
        monkeypatch.setattr(pool_module, "pool", pool)
        try:
            async with pool.acquire() as c:
                # Explicit disposable projection DB only; no live bot tables/migration runner.
                await c.execute(
                    "DROP SCHEMA IF EXISTS product_acceptance CASCADE; CREATE SCHEMA product_acceptance"
                )
            await pool.close()
            pool = await asyncpg.create_pool(
                host=dsn["host"],
                port=int(dsn.get("port", 5432)),
                database=dsn["dbname"],
                user=dsn["user"],
                password=dsn["password"],
                min_size=1,
                max_size=3,
                server_settings={"search_path": "product_acceptance"},
            )
            monkeypatch.setattr(pool_module, "pool", pool)
            async with pool.acquire() as c:
                await c.execute(
                    "CREATE TABLE sellers(id bigint PRIMARY KEY,telegram_id bigint NOT NULL); INSERT INTO sellers VALUES (101,900001)"
                )
                await c.execute(
                    "CREATE TABLE seller_subscriptions(seller_id bigint,slots integer,expires_at timestamptz); INSERT INTO seller_subscriptions VALUES (101,2,now()+interval '10 days')"
                )
                await c.execute(
                    (
                        Path(__file__).parents[2]
                        / "database/migrations/20261114_global_billing_projection.sql"
                    ).read_text()
                )
            order = await gb.create_checkout(101, "garage", 99)
            assert order["url"].startswith("https://billing.example.test/pay/")
            b = await gb.fetchrow(
                "SELECT * FROM global_billing_bindings WHERE seller_id=101"
            )
            await gb.sync_binding(b)
            assert await gb.active_intervals(101, "garage") == []
            event = callback(
                app.state.payments.provider,
                dict(order, amount_minor=9900),
                payment_id="telegram-garage-first",
            )
            assert app.state.payments.callback(**event) == "settled"
            await gb.sync_binding(b)
            await gb.sync_binding(b)
            from bot.database.repositories.seller_repo import get_active_slots

            assert await get_active_slots(101) == 3
            assert await get_active_slots(999) == 0
            monkeypatch.setenv("BOT_GLOBAL_GARAGE_ENABLED", "false")
            assert await get_active_slots(101) == 2
            async with pool.acquire() as c:
                assert (
                    await c.fetchval("SELECT count(*) FROM global_billing_projections")
                    == 1
                )
        finally:
            await pool.close()

    asyncio.run(scenario())


def test_flags_off_keep_legacy_projection_objects_and_checkout(monkeypatch):
    import ast, base64, hashlib, json, uuid, logging
    from bot.services import global_billing as gb

    for flag in gb.PRODUCT_FLAGS.values():
        monkeypatch.delenv(flag, raising=False)
    row = {"seller_id": 77, "crm_enabled": True, "id": 55}

    async def scenario():
        assert await gb.projected_crm(row) is row
        assert await gb.projected_site(row) is row
        assert await gb.active_intervals(77, "garage") == []
        # Execute the existing service class without importing unrelated bot credentials.
        source = (Path(__file__).parents[2] / "services/liqpay_service.py").read_text()
        tree = ast.parse(source)
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        saved = []

        async def create_payment(**kwargs):
            saved.append(kwargs)
            return kwargs

        namespace = dict(
            base64=base64,
            hashlib=hashlib,
            json=json,
            uuid=uuid,
            logger=logging.getLogger("legacy-acceptance"),
            create_payment=create_payment,
            DESCRIPTIONS={"garage_1": "1 авто на розборі"},
        )
        exec(
            compile(
                ast.Module(body=[klass], type_ignores=[]), "<existing-service>", "exec"
            ),
            namespace,
        )
        service = namespace["LiqPayService"](
            "legacy-public-synthetic", "legacy-private-synthetic"
        )
        checkout = await service.create_payment(
            99, "https://legacy.example.test/callback", 77, "garage"
        )
        from urllib.parse import urlsplit, parse_qs

        form = parse_qs(urlsplit(checkout["url"]).query)
        payload = json.loads(base64.b64decode(form["data"][0]))
        assert (
            payload["version"] == "3"
            and payload["amount"] == 99
            and payload["sandbox"] == 1
        )
        assert not gb.canonical_order(checkout["order_id"]) and len(saved) == 1
        assert (
            form["signature"][0]
            == base64.b64encode(
                hashlib.sha1(
                    (
                        "legacy-private-synthetic"
                        + form["data"][0]
                        + "legacy-private-synthetic"
                    ).encode()
                ).digest()
            ).decode()
        )

    asyncio.run(scenario())
