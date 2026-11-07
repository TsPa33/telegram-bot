"""Focused local PostgreSQL + fake source/DeepL, no paid external requests."""

import json
from uuid import uuid4
import httpx, pytest
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.main import app
from app.models import (
    Part,
    Photo,
    Operation,
    PartNameTranslation,
    DismantlingAnnotation,
    VehicleChecklistItem,
    now,
)
from app.services.inventory import snapshot
from app.api.plan_parts import plan_parts_client
from app.services.plan_parts import CatalogPartType
from test_v3_release_audit import all_tables
from conftest import signup


@pytest.fixture
def setup(logged, vehicle):
    with engine().begin() as db:
        db.execute(
            text("UPDATE vehicles SET ktype=123 WHERE id=:id"), {"id": vehicle["id"]}
        )

    class Source:
        def recover_categories(self, *args):
            return [
                CatalogPartType(pt_id=1, name="Starter", article_count=3),
                CatalogPartType(
                    pt_id=2, name="Synthetic unknown unit", article_count=2
                ),
                CatalogPartType(pt_id=3, name="Brake caliper", article_count=1),
            ]

        def categories(self, *a):
            raise AssertionError("No paid call")

    app.dependency_overrides[plan_parts_client] = Source
    r = logged.post(
        "/api/v1/plan-parts/categories/recover?vehicle_id="
        + vehicle["id"]
        + "&ktype=123"
    )
    assert r.status_code == 200, r.text
    yield logged, vehicle
    app.dependency_overrides.pop(plan_parts_client, None)


def url(v, suffix=""):
    return "/api/v1/vehicles/" + v["id"] + "/dismantling-workspace" + suffix


def read(c, v):
    r = c.get(url(v) + "?source=professional")
    assert r.status_code == 200, r.text
    return r.json()


def test_progress_uses_receipts_not_assumed_quantity_and_is_read_only(setup):
    c, v = setup
    made = c.post(
        "/api/v1/plan-parts/donor-parts/add?vehicle_id=" + v["id"],
        json={"ktype": 123, "pt_id": 1, "ukrainian_name": "Стартер"},
    )
    assert made.status_code == 200, made.text
    owner = c.get("/api/v1/auth/me").json()["id"]
    with Session(engine()) as db:
        db.add(
            Part(
                account_id=owner,
                vehicle_id=v["id"],
                name="Припущена",
                quantity=99,
                inventory_origin="virtual_donor",
                quantity_basis="assumed",
                physical_location_kind="on_vehicle",
                compatibility_notes="plan.parts:ktype=123;pt_id=2",
            )
        )
        db.add(
            Photo(
                account_id=owner,
                part_id=made.json()["part_id"],
                filename="synthetic-only.png",
                media_type="image/png",
            )
        )
        db.commit()
        before = all_tables(db)
    d = read(c, v)
    assert d["progress"] == dict(
        planned=2, received=1, with_photo=1, percent=50.0, unit="plan_entries"
    )
    assert d["items"][0]["name"] == "Стартер" and d["items"][1]["state"] == "planned"
    with Session(engine()) as db:
        assert before == all_tables(db)


def test_manual_names_states_and_idempotency_do_not_mutate_stock(setup):
    c, v = setup
    owner = c.get("/api/v1/auth/me").json()["id"]
    with Session(engine()) as db:
        p = Part(
            account_id=owner,
            vehicle_id=v["id"],
            name="Existing",
            quantity=3,
            selling_price="45.67",
            currency="USD",
            article_number="ART",
            article_brand="Brand",
            oem_number="OEM",
            compatibility_notes="plan.parts:ktype=123;pt_id=1",
        )
        db.add(p)
        db.commit()
        pid = p.id
        before = snapshot(p)
    payload = {
        "source": "professional",
        "keys": ["pp:123:1"],
        "action": "rename",
        "name": "Стартер перевірений",
    }
    for _ in range(2):
        assert c.post(url(v, "/annotations"), json=payload).status_code == 200
    for action in ("hide", "restore", "dismantled"):
        r = c.post(
            url(v, "/annotations"),
            json={"source": "professional", "keys": ["pp:123:2"], "action": action},
        )
        assert r.status_code == 200, r.text
    d = read(c, v)
    assert (
        d["items"][0]["name"] == "Стартер перевірений"
        and d["items"][0]["original"] == "Starter"
    )
    assert d["items"][1]["state"] == "dismantled"
    with Session(engine()) as db:
        assert snapshot(db.get(Part, pid)) == before
        assert db.scalar(select(func.count()).select_from(DismantlingAnnotation)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(Operation)
                .where(Operation.type == "dismantling_annotation")
            )
            == 4
        )


def test_deepl_persists_and_replay_never_retranslates_saved_or_manual(
    setup, monkeypatch
):
    c, v = setup
    from app.services import parts_translation as translator

    translator._cache.clear()
    monkeypatch.setenv("WAREHOUSE_DEEPL_API_KEY", "synthetic:fx")
    calls = []
    real = httpx.Client

    def handler(req):
        assert req.url.host == "api-free.deepl.com"
        body = json.loads(req.content)
        calls.extend(body["text"])
        return httpx.Response(
            200,
            json={
                "translations": [{"text": "Синтетичний вузол"} for _ in body["text"]]
            },
        )

    monkeypatch.setattr(
        translator.httpx,
        "Client",
        lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handler)}),
    )
    payload = {"source": "professional", "keys": ["pp:123:1", "pp:123:2"]}
    try:
        for _ in range(2):
            response = c.post(url(v, "/translations"), json=payload)
            assert response.status_code == 200, response.text
        assert calls == ["Synthetic unknown unit"]
        assert read(c, v)["items"][1]["name"] == "Синтетичний вузол"
        assert (
            c.post(
                url(v, "/annotations"),
                json={
                    "source": "professional",
                    "keys": ["pp:123:2"],
                    "action": "rename",
                    "name": "Моя ручна назва",
                },
            ).status_code
            == 200
        )
        assert c.post(url(v, "/translations"), json=payload).status_code == 200
        assert read(c, v)["items"][1]["name"] == "Моя ручна назва" and len(calls) == 1
        with Session(engine()) as db:
            assert db.scalar(select(func.count()).select_from(PartNameTranslation)) == 2
    finally:
        translator._cache.clear()


def test_scope_csrf_and_forged_plan_keys(setup):
    c, v = setup
    with TestClient(app) as other:
        signup(other, "other-plan@example.test")
        assert other.get(url(v)).status_code == 404
        assert (
            other.post(
                url(v, "/annotations"),
                json={"source": "professional", "keys": ["pp:123:1"], "action": "hide"},
            ).status_code
            == 404
        )
    bad = c.post(
        url(v, "/annotations"),
        json={"source": "professional", "keys": ["pp:123:999"], "action": "hide"},
    )
    assert bad.status_code == 404
    assert (
        c.post(
            url(v, "/annotations"),
            headers={"X-CSRF-Token": ""},
            json={"source": "professional", "keys": ["pp:123:1"], "action": "hide"},
        ).status_code
        == 403
    )


def test_unconfigured_translation_never_fabricates_success(setup, monkeypatch):
    c, v = setup
    monkeypatch.delenv("WAREHOUSE_DEEPL_API_KEY", raising=False)
    response = c.post(
        url(v, "/translations"), json={"source": "professional", "keys": ["pp:123:2"]}
    )
    assert response.status_code == 200
    assert response.json()["configured"] is False and response.json()["saved"] == 0
    assert read(c, v)["items"][1]["name"] == "Synthetic unknown unit"


def test_original_name_can_be_added_without_translation_and_replay_is_safe(setup):
    c,v=setup
    endpoint="/api/v1/plan-parts/donor-parts/add?vehicle_id="+v["id"]
    data={"ktype":123,"pt_id":2,"ukrainian_name":"Synthetic unknown unit"}
    first=c.post(endpoint,json=data)
    assert first.status_code==200,first.text
    again=c.post(endpoint,json=data)
    assert again.status_code==200,again.text
    assert first.json()["part_id"]==again.json()["part_id"]
    assert again.json()["quantity"]==1


def test_modification_change_requires_confirmation_preserves_previous_plan(setup):
    c,v=setup
    endpoint="/api/v1/plan-parts/vehicle-modification/select?vehicle_id="+v["id"]
    assert c.post(endpoint,json={"ktype":456}).status_code==409
    assert c.post(endpoint,json={"ktype":456,"confirm_change":True}).status_code==200
    history=c.get("/api/v1/plan-parts/workspace?vehicle_id="+v["id"]).json()
    assert 123 in history["saved_plan_ktypes"]
    assert c.post(endpoint,json={"ktype":123,"confirm_change":True}).status_code==200
    assert len(read(c,v)["items"])==3
