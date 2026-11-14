"""In-process two-service HTTP transport for local browser acceptance only."""

import os
from contextlib import contextmanager
from sqlalchemy.engine import make_url

if (
    os.getenv("WAREHOUSE_E2E") != "1"
    or make_url(os.environ["WAREHOUSE_DATABASE_URL"]).host != "127.0.0.1"
    or not make_url(os.environ["WAREHOUSE_DATABASE_URL"]).database.endswith("_test")
):
    raise RuntimeError("Disposable local browser service only")
from fastapi.testclient import TestClient
from fastapi import Request, HTTPException
from app.main import app
from app.services import global_billing
from bot.billing.tests.global_browser_server import app as finance

client = TestClient(finance)
client.__enter__()

# Replace only the gateway transport, rather than all httpx clients in this process.
original = global_billing.request


class DirectPeer:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @contextmanager
    def stream(self, method, url, **kwargs):
        if not url.startswith("https://billing.example.test/v1/"):
            raise RuntimeError("Local fixture only")
        yield client.request(
            method, url.removeprefix("https://billing.example.test"), **kwargs
        )


# A module-local proxy preserves the real HTTP client used by every other service.
class HTTP:
    Client = DirectPeer
    Timeout = global_billing.httpx.Timeout
    HTTPError = global_billing.httpx.HTTPError


global_billing.httpx = HTTP


@app.post("/api/v1/__billing_fixture/confirm")
async def confirm(request: Request):
    response = client.post(
        "/__fixture/confirm",
        json=await request.json(),
        headers={"X-Fixture-Key": request.headers.get("X-Fixture-Key", "")},
    )
    if response.status_code != 200:
        raise HTTPException(response.status_code)
    return response.json()


@app.get("/api/v1/__billing_fixture/order/{order}")
def check(order: str, request: Request):
    response = client.get(
        "/__fixture/order/" + order,
        headers={"X-Fixture-Key": request.headers.get("X-Fixture-Key", "")},
    )
    if response.status_code != 200:
        raise HTTPException(response.status_code)
    return response.json()
