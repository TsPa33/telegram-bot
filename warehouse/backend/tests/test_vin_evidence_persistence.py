"""Durable VIN restoration from user-supplied API result screenshots.

Offline only: no Vincario credits; never silently replace provider evidence.
"""
from app.services import vin_evidence


def test_restore_three_reports_to_postgres_idempotently(logged, monkeypatch):
    from app.api import vin_vincario_trial as route
    monkeypatch.setattr(route, "platform_admin", lambda _user: True)
    monkeypatch.setattr(route.vin_vincario_trial, "preview",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("Unexpected vendor decode")))
    first=logged.post("/api/v1/vehicles/vin/vincario/trial/restore-controls")
    assert first.status_code==200,first.text
    payload=first.json()
    assert len(payload["created"])==3
    assert payload["provider_requests"]==0
    assert payload["credits_spent"]==0
    second=logged.post("/api/v1/vehicles/vin/vincario/trial/restore-controls")
    assert second.status_code==200,second.text
    assert len(second.json()["already_saved"])==3
    for vin in vin_evidence.CONTROL_REPORTS:
        saved=logged.get("/api/v1/vehicles/vin/vincario/trial/saved?vin="+vin)
        assert saved.status_code==200,saved.text
        obj=saved.json()
        assert obj["from_durable_cache"] is True
        assert obj["source"]=="user_supplied_api_result_screenshot"
        assert obj["vin"]==vin
        preview=logged.post("/api/v1/vehicles/vin/vincario/trial/preview",
            json={"vin":vin,"acknowledge_free_quota":True})
        assert preview.status_code==200,preview.text
        assert preview.json()["from_durable_cache"] is True


def test_missing_vin_evidence_stays_unknown(logged, monkeypatch):
    from app.api import vin_vincario_trial as route
    monkeypatch.setattr(route,"platform_admin",lambda _user:True)
    r=logged.get("/api/v1/vehicles/vin/vincario/trial/saved?vin=WVWZZZ1JZXW000001")
    assert r.status_code==200
    assert r.json()["status"]=="not_saved"


def test_denied_user_cannot_read_or_restore_cache(logged, monkeypatch):
    from app.api import vin_vincario_trial as route
    monkeypatch.setattr(route,"platform_admin",lambda _user:False)
    assert logged.post("/api/v1/vehicles/vin/vincario/trial/restore-controls").status_code==403
    assert logged.get("/api/v1/vehicles/vin/vincario/trial/saved?vin=XLRTE47MS0E774889").status_code==403
