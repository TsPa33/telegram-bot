"""Synthetic local PostgreSQL and MockTransport only; zero live provider calls."""

import json, threading, hashlib
from uuid import uuid4
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session
from pydantic import field_validator
import httpx, pytest
from app.db import engine
from app.models import Account, Part, PlanPartsResponse
from app.models.plan_parts_receipt import PlanPartsArticleReceipt
from app.services.plan_parts_persistence import ResponseStore, PersistenceError
from app.services.plan_parts import (
    PlanPartsClient,
    PlanPartsError,
    RequestGate,
    Article,
)
from app.main import app
from app.api.plan_parts import plan_parts_client
from test_v3_release_audit import all_tables


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "true")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "synthetic-test-secret")
    monkeypatch.setenv("WAREHOUSE_PLAN_PARTS_STORAGE_APPROVED", "true")
    monkeypatch.setenv(
        "WAREHOUSE_PLAN_PARTS_TOKEN_MAXIMA", '{"articles":2,"categories":1}'
    )


def identity(db, logged):
    account = logged.get("/api/v1/auth/me").json()["id"]
    return SimpleNamespace(
        user=db.get(Account, account), workspace_account_id=account, actor_id=account
    )


def payload():
    return {
        "success": True,
        "data": {
            "count": 5,
            "limit": 50,
            "results": [
                {
                    "art_id": 901,
                    "article_nr": "ART-901",
                    "brand": "Test Brand",
                    "part_name": None,
                    "extra_metadata": {
                        "technical": "preserve-original",
                        "oem_references_unverified": ["FIXTURE-OEM"],
                    },
                }
            ],
        },
    }


def client(db, who, v, handler, key=None, confirm=True, force=False):
    return PlanPartsClient(
        httpx.MockTransport(handler),
        store=ResponseStore(db, who, v["id"], key or str(uuid4()), confirm, 2, force),
    )


def test_raw_snapshot_extra_fields_partial_metadata_and_restart(
    logged, vehicle, monkeypatch
):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=payload())

    with Session(engine()) as db:
        who = identity(db, logged)
        key = str(uuid4())
        c = client(db, who, vehicle, handler, key)
        before = all_tables(db)
        r = c.articles(who.workspace_account_id, 123, 456, RequestGate())
        assert len(r) == 1
        after = all_tables(db)
        assert {k: v for k, v in before.items() if k != "plan_parts_responses"} == {
            k: v for k, v in after.items() if k != "plan_parts_responses"
        }
        saved = db.scalar(select(PlanPartsResponse))
        rid = saved.id
        assert (
            saved.status == "validated"
            and json.loads(saved.body)["data"]["results"][0]["extra_metadata"][
                "technical"
            ]
            == "preserve-original"
        )
        assert saved.sha256 == hashlib.sha256(saved.body).hexdigest()
        assert (
            saved.metadata_json["provider_total"] == 5
            and saved.metadata_json["returned_count"] == 1
            and saved.metadata_json["completeness"] == "partial"
        )
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "false")
    monkeypatch.setenv("PLAN_PARTS_API_KEY", "")
    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(db, who, vehicle, lambda r: pytest.fail("No network on replay"), key)
        assert c.articles(who.workspace_account_id, 123, 456)[0].article_nr == "ART-901"
        assert (
            len(calls) == 1
            and db.scalar(select(func.count()).select_from(PlanPartsResponse)) == 1
        )
    response = logged.get("/api/v1/plan-parts/responses/" + rid)
    assert response.status_code == 200
    assert (
        response.headers["x-content-sha256"]
        == hashlib.sha256(response.content).hexdigest()
    )


def test_invalid_paid_200_survives_restart_and_parser_repair(
    logged, vehicle, monkeypatch
):
    body = payload()
    body["data"]["results"][0]["art_id"] = "901"
    calls = []
    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(
            db,
            who,
            vehicle,
            lambda req: (calls.append(1) or httpx.Response(200, json=body)),
        )
        with pytest.raises(PlanPartsError):
            c.articles(who.workspace_account_id, 123, 456, RequestGate())
        row = db.scalar(select(PlanPartsResponse))
        assert row.body and row.status == "invalid"

    class Repaired(Article):
        @field_validator("art_id", mode="before")
        @classmethod
        def integer_id(cls, value):
            return int(value)

    monkeypatch.setattr("app.services.plan_parts.Article", Repaired)
    monkeypatch.setenv("PLAN_PARTS_ENABLED", "false")
    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(db, who, vehicle, lambda req: pytest.fail("Repair must be free"))
        assert c.recover_articles(who.workspace_account_id, 123, 456)[0].art_id == 901
        assert (
            len(calls) == 1
            and db.scalar(select(PlanPartsResponse)).status == "validated"
        )


def test_timeout_intent_blocks_fresh_payment_and_replay(logged, vehicle):
    calls = []

    def timeout(req):
        calls.append(1)
        raise httpx.ReadTimeout("synthetic")

    key = str(uuid4())
    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(db, who, vehicle, timeout, key)
        with pytest.raises(PlanPartsError) as exc:
            c.articles(who.workspace_account_id, 123, 456, RequestGate())
        assert (
            exc.value.status == 504
            and db.scalar(select(PlanPartsResponse)).status == "uncertain"
        )
    for request_key in [key, str(uuid4())]:
        with Session(engine()) as db:
            who = identity(db, logged)
            c = client(
                db,
                who,
                vehicle,
                lambda req: pytest.fail("No second payment"),
                request_key,
                force=True,
            )
            with pytest.raises(PlanPartsError) as exc:
                c.articles(who.workspace_account_id, 123, 456, RequestGate())
            assert exc.value.status == 409
    assert len(calls) == 1


def test_parallel_context_and_exact_key_idempotency(logged, vehicle):
    with Session(engine()) as db:
        owner = identity(db, logged).actor_id
    entered = threading.Event()
    release = threading.Event()
    calls = []
    key = str(uuid4())

    def work(request_key):
        with Session(engine()) as db:
            who = SimpleNamespace(
                user=db.get(Account, owner), actor_id=owner, workspace_account_id=owner
            )

            def handler(req):
                calls.append(1)
                entered.set()
                assert release.wait(10)
                return httpx.Response(200, json=payload())

            c = client(db, who, vehicle, handler, request_key)
            try:
                return c.articles(owner, 123, 456, RequestGate())
            except PlanPartsError as e:
                return e.status

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(work, key)
        assert entered.wait(10)
        second = pool.submit(work, str(uuid4()))
        assert second.result(10) == 409
        release.set()
        assert len(first.result(10)) == 1
    with Session(engine()) as db:
        who = SimpleNamespace(
            user=db.get(Account, owner), actor_id=owner, workspace_account_id=owner
        )
        assert (
            len(
                client(db, who, vehicle, lambda r: pytest.fail("replay"), key).articles(
                    owner, 123, 456
                )
            )
            == 1
        )
    assert len(calls) == 1


def test_capture_redacts_secret_and_pii_unknown_public_fields_preserved(
    logged, vehicle
):
    body = payload()
    body["token"] = "synthetic-test-secret"
    body["data"]["email"] = "private@example.test"
    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(db, who, vehicle, lambda r: httpx.Response(200, json=body))
        c.articles(who.actor_id, 123, 456, RequestGate())
        r = db.scalar(select(PlanPartsResponse))
        assert (
            b"synthetic-test-secret" not in r.body
            and b"private@example.test" not in r.body
        )
        assert b"preserve-original" in r.body and r.metadata_json["redacted"]


def test_no_tariff_or_confirmation_no_network_or_request_receipt(
    logged, vehicle, monkeypatch
):
    for cost, confirm in [("{}", True), ('{"articles":2}', False)]:
        monkeypatch.setenv("WAREHOUSE_PLAN_PARTS_TOKEN_MAXIMA", cost)
        with Session(engine()) as db:
            who = identity(db, logged)
            c = client(
                db,
                who,
                vehicle,
                lambda r: pytest.fail("No paid request"),
                confirm=confirm,
            )
            with pytest.raises(PlanPartsError) as exc:
                c.articles(who.actor_id, 123, 456, RequestGate())
            assert exc.value.status in (503, 428)
            assert db.scalar(select(func.count()).select_from(PlanPartsResponse)) == 0


def test_saved_workspace_classification_and_no_writes(logged, vehicle):
    r = logged.get("/api/v1/plan-parts/workspace?vehicle_id=" + vehicle["id"])
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["types"] == 0 and not r.json()["policy"]["oem_available"]
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(PlanPartsResponse)) == 0


def test_assignment_relocks_after_receipt_commit_rejects_archived_target(
    logged, vehicle, monkeypatch
):
    from app.api import plan_parts as route

    with engine().begin() as conn:
        conn.execute(
            text("UPDATE vehicles SET ktype=123 WHERE id=:id"), {"id": vehicle["id"]}
        )

    class Provider:
        def recover_categories(self, *a):
            return [SimpleNamespace(pt_id=456)]

        def recover_articles(self, *a):
            return [Article(art_id=901, article_nr="ART", brand="Brand")]

    app.dependency_overrides[plan_parts_client] = Provider
    try:
        part = logged.post(
            "/api/v1/plan-parts/donor-parts/add?vehicle_id=" + vehicle["id"],
            json={"ktype": 123, "pt_id": 456, "ukrainian_name": "Генератор"},
        ).json()["part_id"]
        original = route._mark_article_receipt

        def mark(*args, **kwargs):
            result = original(*args, **kwargs)
            with engine().begin() as conn:
                conn.execute(
                    text("UPDATE parts SET archived=true WHERE id=:id"), {"id": part}
                )
            return result

        monkeypatch.setattr(route, "_mark_article_receipt", mark)
        response = logged.post(
            "/api/v1/plan-parts/donor-parts/article/select?vehicle_id=" + vehicle["id"],
            json={"ktype": 123, "pt_id": 456, "part_id": part, "art_id": 901},
        )
        assert response.status_code in (404, 409), response.text
        with Session(engine()) as db:
            assert db.get(Part, part).article_number == ""
    finally:
        app.dependency_overrides.pop(plan_parts_client, None)


def test_empty_result_replay_and_immutable_body(logged, vehicle):
    from sqlalchemy.exc import DBAPIError

    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(db, who, vehicle, lambda r: httpx.Response(200, json=[]))
        assert c.articles(who.actor_id, 123, 456, RequestGate()) == []
        row = db.scalar(select(PlanPartsResponse))
        original = row.body
        row.body = b"changed"
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()
        assert db.get(PlanPartsResponse, row.id).body == original
    with Session(engine()) as db:
        who = identity(db, logged)
        c = client(
            db, who, vehicle, lambda r: pytest.fail("empty is a valid saved response")
        )
        assert c.recover_articles(who.actor_id, 123, 456) == []


def test_capture_db_failure_keeps_intent_and_forbids_paid_retry(
    logged, vehicle, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError

    calls = []
    with Session(engine()) as db:
        who = identity(db, logged)
        original = db.commit

        def commit():
            if any(
                isinstance(r, PlanPartsResponse) and r.body is not None
                for r in db.dirty
            ):
                raise SQLAlchemyError("synthetic storage failure")
            original()

        monkeypatch.setattr(db, "commit", commit)
        c = client(
            db,
            who,
            vehicle,
            lambda r: (calls.append(1) or httpx.Response(200, json=payload())),
        )
        with pytest.raises(PlanPartsError) as exc:
            c.articles(who.actor_id, 123, 456, RequestGate())
        assert exc.value.status == 503
    with Session(engine()) as db:
        who = identity(db, logged)
        assert db.scalar(select(PlanPartsResponse)).status == "pending"
        with pytest.raises(PlanPartsError) as exc:
            client(
                db, who, vehicle, lambda r: pytest.fail("no retry"), force=True
            ).articles(who.actor_id, 123, 456, RequestGate())
        assert exc.value.status == 409
    assert len(calls) == 1


def test_other_workspace_cannot_read_saved_response(logged, vehicle):
    from fastapi.testclient import TestClient
    from conftest import signup

    with Session(engine()) as db:
        who = identity(db, logged)
        client(
            db, who, vehicle, lambda r: httpx.Response(200, json=payload())
        ).articles(who.actor_id, 123, 456, RequestGate())
        rid = db.scalar(select(PlanPartsResponse.id))
    with TestClient(app) as other:
        signup(other, "other-workspace@example.test")
        assert other.get("/api/v1/plan-parts/responses/" + rid).status_code == 404
        assert (
            other.get(
                "/api/v1/plan-parts/workspace?vehicle_id=" + vehicle["id"]
            ).status_code
            == 404
        )


def test_same_catalogue_context_reused_for_second_owned_donor(
    logged, vehicle, vehicle_data
):
    second = logged.post(
        "/api/v1/vehicles", json={**vehicle_data, "donor_id": "SECOND-LOCAL-ONLY"}
    ).json()
    with Session(engine()) as db:
        who = identity(db, logged)
        client(
            db, who, vehicle, lambda r: httpx.Response(200, json=payload())
        ).articles(who.actor_id, 123, 456, RequestGate())
    with Session(engine()) as db:
        who = identity(db, logged)
        assert (
            len(
                client(
                    db,
                    who,
                    second,
                    lambda r: pytest.fail("Same query must reuse owned response"),
                ).articles(who.actor_id, 123, 456, RequestGate())
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(PlanPartsResponse)) == 1


def test_manual_card_edit_never_keeps_stale_provider_reference(logged, part):
    with engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE parts SET article_number='OLD-API',article_brand='Old provider',article_provenance='{\"source\":\"plan.parts\"}'::json WHERE id=:id"
            ),
            {"id": part["id"]},
        )
    before = logged.get("/api/v1/parts/" + part["id"]).json()
    from app.schemas import PartInput
    body={k:v for k,v in before.items() if k in PartInput.model_fields}
    changed = logged.put('/api/v1/parts/'+part['id'],json={**body,'article_number':'MANUAL-NEW','oem_number':'MANUAL-OEM'})
    assert changed.status_code == 200, changed.text
    row = changed.json()
    assert (
        row["article_brand"] == ""
        and row["article_provenance"]["source"] == "manual"
        and row["oem_provenance"]["source"] == "manual"
    )
    for key in (
        "quantity",
        "reserved_quantity",
        "selling_price",
        "currency",
        "unit_cost",
    ):
        assert row[key] == before[key]
    body = {k: v for k, v in row.items() if k in PartInput.model_fields and k not in ("article_number", "oem_number")}
    preserved = logged.put("/api/v1/parts/" + part["id"], json=body)
    assert preserved.status_code == 200, preserved.text
    assert (
        preserved.json()["article_number"] == "MANUAL-NEW"
        and preserved.json()["oem_number"] == "MANUAL-OEM"
    )
