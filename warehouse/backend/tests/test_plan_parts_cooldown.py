"""Local Plan.Parts request gate is bounded and recovers in 30 seconds."""
import pytest
from app.services.plan_parts import RequestGate, PlanPartsError


def test_duplicate_lookup_recovers_after_30_seconds():
    now = [100.0]
    gate = RequestGate(clock=lambda: now[0])
    gate.acquire("owner", "categories[131094]")
    with pytest.raises(PlanPartsError) as exc:
        gate.acquire("owner", "categories[131094]")
    assert exc.value.status == 429
    assert exc.value.retry_after == 30
    now[0] += 14
    with pytest.raises(PlanPartsError) as exc:
        gate.acquire("owner", "categories[131094]")
    assert exc.value.retry_after == 16
    now[0] += 16
    gate.acquire("owner", "categories[131094]")


def test_account_burst_has_retry_time_and_recovers():
    now = [100.0]
    gate = RequestGate(clock=lambda: now[0])
    for k in range(10):
        gate.acquire("owner", f"articles:{k}")
    with pytest.raises(PlanPartsError) as exc:
        gate.acquire("owner", "articles:next")
    assert exc.value.retry_after == 30
    now[0] += 30
    gate.acquire("owner", "articles:next")
