"""Run only after tests/vehicle_workspace_server.py, using synthetic local data."""

import json, os
from uuid import uuid4
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session
from tests.vehicle_workspace_server import app
from app.db import engine

with httpx.Client(base_url="http://127.0.0.1:8022") as c:
    email = "workspace-" + str(uuid4())[:8] + "@example.test"
    r = c.post(
        "/api/v1/auth/register",
        json=dict(
            name="Синтетичний власник",
            email=email,
            password="local-workspace-only-password",
        ),
    )
    assert r.status_code == 201, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    owner = r.json()["user"]["id"]
    r = c.post(
        "/api/v1/vehicles",
        json=dict(
            manufacturer="Volvo",
            model="XC40",
            year=2018,
            donor_id="LOCAL-SYNTHETIC",
            acquisition_date="2026-01-01",
            acquisition_cost="0",
            ktype=131094,
        ),
    )
    assert r.status_code == 201, r.text
    vehicle = r.json()
    r = c.post(
        "/api/v1/plan-parts/categories/lookup",
        params=dict(
            vehicle_id=vehicle["id"],
            ktype=131094,
            request_key=str(uuid4()),
            confirm_paid="true",
            max_tokens=1,
        ),
    )
    assert r.status_code == 200, r.text
    with engine().begin() as db:
        db.execute(
            text(
                "UPDATE vehicle_checklist_items SET name_uk=CASE name_en WHEN 'Starter' THEN 'Стартер' WHEN 'Alternator' THEN 'Генератор' WHEN 'Brake caliper' THEN 'Гальмівний супорт' ELSE 'Фара' END WHERE vehicle_id=:id"
            ),
            dict(id=vehicle["id"]),
        )
    r = c.post(
        "/api/v1/plan-parts/donor-parts/add",
        params=dict(vehicle_id=vehicle["id"]),
        json=dict(ktype=131094, pt_id=1, ukrainian_name="Стартер"),
    )
    assert r.status_code == 200, r.text
    part = r.json()["part_id"]
    r = c.post(
        "/api/v1/plan-parts/articles/lookup",
        params=dict(
            vehicle_id=vehicle["id"],
            ktype=131094,
            pt_id=1,
            request_key=str(uuid4()),
            confirm_paid="true",
            max_tokens=2,
        ),
    )
    assert r.status_code == 200, r.text
    with open("/tmp/vehicle-workspace-fixture.json", "w") as f:
        json.dump(
            dict(
                email=email,
                password="local-workspace-only-password",
                owner=owner,
                vehicle=vehicle,
                part=part,
                synthetic=True,
            ),
            f,
        )
print("Synthetic fixture ready; no external API calls")
