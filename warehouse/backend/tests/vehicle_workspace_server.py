"""Guarded local synthetic API for browser acceptance. Never use against staging."""

import os, inspect
from urllib.parse import urlsplit

url = os.getenv("WAREHOUSE_DATABASE_URL", "")
parsed = urlsplit(url)
if (
    os.getenv("WAREHOUSE_E2E") != "1"
    or parsed.hostname != "127.0.0.1"
    or parsed.port != 55440
    or not parsed.path.endswith("_test")
):
    raise RuntimeError("Dedicated local fixture DB required")
os.environ.update(
    WAREHOUSE_CATALOGUE_WORKER_ENABLED="false",
    WAREHOUSE_COOKIE_SECURE="false",
    PLAN_PARTS_ENABLED="true",
    PLAN_PARTS_API_KEY="synthetic-fixture-key",
    WAREHOUSE_DEEPL_API_KEY="",
    WAREHOUSE_PLAN_PARTS_STORAGE_APPROVED="true",
    WAREHOUSE_PLAN_PARTS_TOKEN_MAXIMA='{"categories":1,"articles":2,"ktype":1}',
)
import httpx
from app.main import app
from app.api.plan_parts import plan_parts_client

original = plan_parts_client
calls = []


def transport(request):
    calls.append(request.url.path)
    if request.url.path.endswith("/categories"):
        rows = [
            dict(
                pt_id=i + 1,
                name=["Starter", "Alternator", "Brake caliper", "Headlight"][i % 4],
                article_count=3,
            )
            for i in range(96)
        ]
    elif request.url.path.endswith("/articles"):
        pt = int(request.url.params["pt_id"])
        rows = [
            dict(
                art_id=pt * 100 + j,
                article_nr=f"SYN-{pt}-{j}",
                brand="Synthetic Brand",
                part_name="Synthetic fixture only",
                extra={"technical": "preserved"},
                attributes={"Specification":"synthetic-only"},
            )
            for j in range(1, 4)
        ]
    else:
        raise AssertionError("Unapproved fixture request")
    return httpx.Response(
        200,
        json=dict(success=True, data=dict(count=len(rows), limit=100, results=rows)),
    )


def mocked(*args, **kwargs):
    client = original(*args, **kwargs)
    client._transport = httpx.MockTransport(transport)
    return client


mocked.__signature__ = inspect.signature(original)
app.dependency_overrides[plan_parts_client] = mocked
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8022)
