"""Validate that Aleto's optional proxy cannot redirect through an arbitrary host."""
from fastapi import HTTPException
from app.api.aleto_control import worker_proxy
import pytest


def test_aleto_private_proxy_guard(monkeypatch):
    monkeypatch.delenv('WAREHOUSE_ALETO_WORKER_PROXY', raising=False)
    assert worker_proxy() is None
    good = 'http://carpot-aleto-tailnet.railway.internal:1056'
    monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_PROXY', good)
    assert worker_proxy() == good
    for raw in ('https://evil.example', 'http://evil.example:1056',
                'http://attacker@carpot-aleto-tailnet.railway.internal:1056',
                'http://carpot-aleto-tailnet.railway.internal:1056/path'):
        monkeypatch.setenv('WAREHOUSE_ALETO_WORKER_PROXY', raw)
        with pytest.raises(HTTPException) as exc:
            worker_proxy()
        assert exc.value.status_code == 503
