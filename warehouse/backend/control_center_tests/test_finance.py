from app.control_center.finance import read_finance
from app.control_center.models import SourceLink, Company, now
import httpx


def test_finance_failure_does_not_write_or_leak(db, monkeypatch):
    c = Company(
        environment="local",
        workspace_id="w",
        display_name="Company",
        search_text="company",
        registered_at=now(),
        fetched_at=now(),
        snapshot={},
    )
    db.add(c)
    db.flush()
    db.add(
        SourceLink(
            company_id=c.id,
            system="billing",
            environment="sandbox",
            entity_type="binding",
            source_id="binding-1",
            status="verified",
            evidence="local",
        )
    )
    db.commit()
    monkeypatch.setenv("CONTROL_CENTER_BILLING_URL", "https://billing.example.test")
    monkeypatch.setenv(
        "CONTROL_CENTER_BILLING_KEY", "synthetic-control-staff-key-1234567890"
    )

    def failed(*a, **kw):
        raise httpx.ConnectError("private network connection details")

    monkeypatch.setattr(httpx, "Client", failed)
    r = read_finance(db, c)
    assert r == dict(
        state="unavailable", reason="billing_read_failed", environment="sandbox"
    )
